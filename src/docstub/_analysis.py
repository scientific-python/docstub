"""Collect type information."""

import builtins
import importlib
import json
import logging
import re
from dataclasses import asdict, dataclass
from functools import cache
from pathlib import Path

import libcst as cst
import libcst.matchers as cstm

from ._utils import accumulate_qualname, module_name_from_path, pyfile_checksum

logger: logging.Logger = logging.getLogger(__name__)


def _shared_leading_qualname(*qualnames):
    """Identify the common leading parts between fully qualified names.

    Parameters
    ----------
    *qualnames : tuple[str]

    Returns
    -------
    shared : str
        The names, still split by ".", that are common to the start of all given
        `qualnames`. Empty string if nothing is common.

    Examples
    --------
    >>> _shared_leading_qualname("foo.bar", "foo.baz")
    'foo'
    >>> _shared_leading_qualname("foo.bar", "faa.baz")
    ''
    """
    if len(qualnames) < 2:
        raise ValueError("need more than two paths")
    splits = (p.split(".") for p in qualnames)
    shared = []
    for names in zip(*splits, strict=False):
        if all(names[0] == p for p in names):
            shared.append(names[0])
        else:
            break
    return ".".join(shared)


@dataclass(slots=True, frozen=True)
class PyImport:
    """Information to construct an import statement for any Python object.

    Attributes
    ----------
    from_ :
        Dotted names after "from".
    import_ :
        Dotted names after "import".
    as_ :
        Name (without ".") after "as".
    implicit :
        Describes an object that doesn't need an import statement and is
        implicitly available. This may be a builtin or an object that is known
        to be available in a given scope. E.g. it may have already been
        imported.

    Examples
    --------
    >>> str(PyImport(from_="numpy", import_="uint8", as_="ui8"))
    'from numpy import uint8 as ui8'

    >>> str(PyImport(implicit="int"))
    Traceback (most recent call last):
        ...
    RuntimeError: cannot import implicit object: 'int'
    """

    import_: str | None = None
    from_: str | None = None
    as_: str | None = None
    implicit: str | None = None

    @classmethod
    @cache
    def typeshed_Incomplete(cls):
        """Create import corresponding to ``from _typeshed import Incomplete``.

        This type is not actually available at runtime and only intended to be
        used in stub files [1]_.

        Returns
        -------
        import : PyImport
            The import corresponding to ``from _typeshed import Incomplete``.

        References
        ----------
        .. [1] https://typing.readthedocs.io/en/latest/guides/writing_stubs.html#incomplete-stubs
        """
        import_ = cls(from_="_typeshed", import_="Incomplete")
        return import_

    def format_import(self, relative_to=None):
        """Format import as valid Python import statement.

        Parameters
        ----------
        relative_to : str, optional
            If a dot-delimited module name is given, format the import relative
            to it.

        Returns
        -------
        formatted : str
        """
        if self.implicit:
            msg = f"cannot import implicit object: {self.implicit!r}"
            raise RuntimeError(msg)
        out = f"import {self.import_}"

        import_path = self.from_
        if import_path:
            if relative_to:
                shared = _shared_leading_qualname(relative_to, import_path)
                if shared == import_path:
                    import_path = "."
                else:
                    import_path = self.from_.replace(shared, "")

            out = f"from {import_path} {out}"
        if self.as_:
            out = f"{out} as {self.as_}"
        return out

    @property
    def target(self) -> str:
        if self.as_:
            out = self.as_
        elif self.import_:
            out = self.import_
        elif self.implicit:
            # Account for scoped form "some_module_scope:target"
            out = self.implicit.split(":")[-1]
        else:
            raise RuntimeError("cannot determine import target")
        return out

    @property
    def has_import(self):
        return self.implicit is None

    def __post_init__(self):
        if self.implicit is not None:
            if (
                self.import_ is not None
                or self.as_ is not None
                or self.from_ is not None
            ):
                raise ValueError("implicit import cannot contain import information")
        elif self.import_ is None:
            raise ValueError("must set at least one parameter: `import_` or `implicit`")
        if self.as_ is not None and "." in self.as_:
            raise ValueError("parameter `as_` can't contain a '.'")

    def __repr__(self) -> str:
        if self.implicit:
            kwargs = f"implicit={self.implicit!r}"
        else:
            kwargs = [
                f"from_={self.from_!r}" if self.from_ else None,
                f"import_={self.import_!r}" if self.import_ else None,
                f"as_={self.as_!r}" if self.as_ else None,
            ]
            kwargs = [arg for arg in kwargs if arg is not None]
            kwargs = ", ".join(kwargs)
        out = f"{type(self).__name__}({kwargs})"
        return out

    def __str__(self) -> str:
        out = self.format_import()
        return out


def _is_type(value):
    """Check if value is a type.

    Parameters
    ----------
    value : Any

    Returns
    -------
    is_type : bool
    """
    # Checking for isinstance(..., type) isn't enough, some types such as
    # typing.Literal don't pass that check. So combine with checking for a
    # __class__ attribute. Not sure about edge cases!
    is_type = isinstance(value, type) or hasattr(value, "__class__")
    return is_type


def _builtin_types():
    """Return known imports for all builtins in the current runtime.

    Returns
    -------
    types : dict[str, PyImport]
    """
    known_builtins = set(dir(builtins))

    types = {}
    for name in known_builtins:
        if name.startswith("_"):
            continue
        value = getattr(builtins, name)
        if not _is_type(value):
            continue
        types[name] = PyImport(implicit=name)

    return types


def _runtime_types_in_module(module_name):
    """Return types of a module in the current runtime.

    Parameters
    ----------
    module_name : str

    Returns
    -------
    types : dict[str, PyImport]
    """
    module = importlib.import_module(module_name)
    types = {}
    for name in module.__all__:
        if name.startswith("_"):
            continue
        value = getattr(module, name)
        if not _is_type(value):
            continue

        py_import = PyImport(from_=module_name, import_=name)
        types[name] = py_import
        types[f"{module_name}.{name}"] = py_import

    return types


def common_known_types():
    """Return commonly supported types.

    This includes builtin types, and types from the `typing` or
    `collections.abc` module.

    Returns
    -------
    py_imports : dict[str, PyImport]

    Examples
    --------
    >>> types = common_known_types()
    >>> types["str"]
    PyImport(implicit='str')
    >>> types["Iterable"]
    PyImport(from_='collections.abc', import_='Iterable')
    >>> types["collections.abc.Iterable"]
    PyImport(from_='collections.abc', import_='Iterable')
    """
    types = _builtin_types()
    types |= _runtime_types_in_module("typing")
    # Overrides containers from typing
    types |= _runtime_types_in_module("collections.abc")
    types |= _runtime_types_in_module("types")
    return types


class TypeCollector(cst.CSTVisitor):
    """Collect types from a given Python file.

    Examples
    --------
    >>> types, prefixes = TypeCollector.collect(__file__)
    >>> types[f"{__name__}.TypeCollector"]
    PyImport(from_='docstub._analysis', import_='TypeCollector')

    >>> from pathlib import Path
    >>> from docstub._utils import module_name_from_path
    >>> module = module_name_from_path(Path(__file__))
    >>> prefixes[f"{module}:logging"]
    PyImport(implicit='...:logging')
    """

    class ImportSerializer:
        """Implements the `FuncSerializer` protocol to cache `TypeCollector.collect`.

        Attributes
        ----------
        suffix : ClassVar[str]
        encoding : ClassVar[str]
        """

        suffix = ".json"
        encoding = "utf-8"

        def hash_args(self, path: Path) -> str:
            """Compute a unique hash from the path passed to `TypeCollector.collect`."""
            key = pyfile_checksum(path)
            return key

        def serialize(self, data):
            """Serialize results from `TypeCollector.collect`.

            Parameters
            ----------
            data : tuple[dict[str, PyImport], dict[str, PyImport]]

            Returns
            -------
            raw : bytes
            """
            primitives = {}
            for name, table in zip(["types", "type_prefixes"], data, strict=False):
                primitives[name] = {key: asdict(imp) for key, imp in table.items()}
            raw = json.dumps(primitives, separators=(",", ":"), indent=1).encode(
                self.encoding
            )
            return raw

        def deserialize(self, raw):
            """Deserialize results from `TypeCollector.collect`.

            Parameters
            ----------
            raw : bytes

            Returns
            -------
            types : dict[str, PyImport]
            type_prefixes : dict[str, PyImport]
            """
            primitives = json.loads(raw.decode(self.encoding))

            def deserialize_table(table):
                return {key: PyImport(**kw) for key, kw in table.items()}

            types = deserialize_table(primitives["types"])
            type_prefixes = deserialize_table(primitives["type_prefixes"])
            return types, type_prefixes

    @classmethod
    def collect(cls, file):
        """Collect importable type annotations in given file.

        Parameters
        ----------
        file : Path

        Returns
        -------
        types : dict[str, PyImport]
        type_prefixes : dict[str, PyImport]
        """
        file = Path(file)
        with file.open("r") as fo:
            source = fo.read()

        tree = cst.parse_module(source)
        collector = cls(module_name=module_name_from_path(file))
        tree.visit(collector)
        return collector.types, collector.type_prefixes

    def __init__(self, *, module_name):
        """Initialize type collector.

        Parameters
        ----------
        module_name : str
        """
        self.module_name = module_name
        self._stack = []
        self.types = {}
        self.type_prefixes = {}

    def visit_ClassDef(self, node: cst.ClassDef) -> bool:
        self._stack.append(node.name.value)
        self._collect_type_annotation(self._stack)
        return True

    def leave_ClassDef(self, original_node: cst.ClassDef) -> None:
        self._stack.pop()

    def visit_FunctionDef(self, node: cst.FunctionDef) -> bool:
        return False

    def visit_TypeAlias(self, node: cst.TypeAlias) -> bool:
        """Collect type alias with 3.12 syntax."""
        stack = [*self._stack, node.name.value]
        self._collect_type_annotation(stack)
        return False

    def visit_AnnAssign(self, node: cst.AnnAssign) -> bool:
        """Collect type alias annotated with `TypeAlias`."""
        is_type_alias = cstm.matches(
            node,
            cstm.AnnAssign(
                annotation=cstm.Annotation(annotation=cstm.Name(value="TypeAlias"))
            ),
        )
        if is_type_alias and node.value is not None:
            names = cstm.findall(node.target, cstm.Name())
            assert len(names) == 1
            stack = [*self._stack, names[0].value]
            self._collect_type_annotation(stack)
        return False

    def visit_ImportFrom(self, node: cst.ImportFrom) -> bool:
        """Collect "from import" targets as usable types."""
        if cstm.matches(node.names, cstm.ImportStar()):
            return False

        if node.module:
            from_names = cstm.findall(node.module, cstm.Name())
            from_names = [n.value for n in from_names]
        else:
            from_names = []

        for import_alias in node.names:
            asname = import_alias.evaluated_alias
            name = import_alias.evaluated_name

            if not node.relative:
                key = ".".join([*from_names, name])
                py_import = PyImport(from_=".".join(from_names), import_=name)
                self.types[key] = py_import

            scoped_key = f"{self.module_name}:{asname or name}"
            scoped_import = PyImport(implicit=scoped_key)
            self.types[scoped_key] = scoped_import

        return False

    def visit_Import(self, node: cst.Import) -> bool:
        for import_alias in node.names:
            asname = import_alias.evaluated_alias
            name = import_alias.evaluated_name
            scoped_key = f"{self.module_name}:{asname or name}"
            py_import = PyImport(implicit=scoped_key)
            self.type_prefixes[scoped_key] = py_import

        return False

    def _collect_type_annotation(self, stack):
        """Collect an importable type annotation.

        Parameters
        ----------
        stack : Iterable[str]
            A list of names that form the path to the collected type.
        """
        qualname = ".".join([self.module_name, *stack])
        py_import = PyImport(from_=self.module_name, import_=stack[0])
        self.types[qualname] = py_import


class TypeMatcher:
    """Match strings to collected type information.

    Attributes
    ----------
    types : dict[str, PyImport]
    type_prefixes : dict[str, PyImport]
    type_nicknames : dict[str, str]
    successful_queries : int
    unknown_qualnames : list
    current_file : Path | None

    Examples
    --------
    >>> from docstub._analysis import TypeMatcher, common_known_types
    >>> db = TypeMatcher()
    >>> db.match("Any")
    ('Any', PyImport(from_='typing', import_='Any'))
    """

    def __init__(
        self,
        *,
        types=None,
        type_prefixes=None,
        type_nicknames=None,
    ):
        """
        Parameters
        ----------
        types : dict[str, PyImport]
        type_prefixes : dict[str, PyImport]
        type_nicknames : dict[str, str]
        """
        self.types = common_known_types() | (types or {})
        self.type_prefixes = type_prefixes or {}
        self.type_nicknames = type_nicknames or {}

        self.stats = {
            "matched_type_names": 0,
            "unknown_type_names": [],
        }

        self.current_file = None

    def _resolve_nickname(self, name):
        """Return intended name if `name` is a nickname.

        Parameters
        ----------
        name : str

        Returns
        -------
        resolved : str
        """
        original = name
        resolved = name
        for _ in range(1000):
            name = self.type_nicknames.get(name)
            if name is None:
                break
            resolved = name
        else:
            logger.warning(
                "Reached limit while resolving nicknames for %r in %s, using %r",
                original,
                self.current_file or "<file not known>",
                resolved,
            )
        return resolved

    def match(self, search):
        """Search for a known annotation name.

        Parameters
        ----------
        search : str
        current_module : Path, optional

        Returns
        -------
        type_name : str | None
        py_import : PyImport | None
        """
        original_search = search
        type_name = None
        py_import = None

        module = module_name_from_path(self.current_file) if self.current_file else None

        search = self._resolve_nickname(search)

        if search.startswith("~."):
            # Sphinx like matching with abbreviated name
            pattern = search.replace(".", r"\.")
            pattern = pattern.replace("~", ".*")
            regex = re.compile(pattern + "$")
            # Might be slow, but works for now
            matches = {
                key: value
                for key, value in self.types.items()
                if regex.match(key)
                if ":" not in key
            }
            if len(matches) > 1:
                shortest_key = sorted(matches.keys(), key=lambda x: len(x))[0]
                py_import = matches[shortest_key]
                type_name = shortest_key
                logger.warning(
                    "%r (original %r) in %s matches multiple types %r, using %r",
                    search,
                    original_search,
                    self.current_file or "<file?>",
                    matches.keys(),
                    shortest_key,
                )
            elif len(matches) == 1:
                type_name, py_import = matches.popitem()
            else:
                search = search[2:]
                logger.debug(
                    "couldn't match %r in %s",
                    search,
                    self.current_file or "<file not known>",
                )

        if py_import is None and module:
            # Look for matching type in current module
            py_import = self.types.get(f"{module}:{search}")
            py_import = self.types.get(f"{module}.{search}", py_import)
            if py_import:
                type_name = search

        if py_import is None and search in self.types:
            type_name = search
            py_import = self.types[search]

        if py_import is None:
            # Try a subset of the qualname (first 'a.b.c', then 'a.b' and 'a')
            for partial_qualname in reversed(accumulate_qualname(search)):
                py_import = self.type_prefixes.get(f"{module}:{partial_qualname}")
                py_import = self.type_prefixes.get(partial_qualname, py_import)
                if py_import:
                    type_name = search
                    break

        if (
            py_import is not None
            and type_name is not None
            and type_name != py_import.target
            and not type_name.startswith(py_import.target)
        ):
            # Ensure that the annotation matches the import target
            type_name = type_name[type_name.find(py_import.target) :]

        if type_name is not None:
            self.stats["matched_type_names"] += 1
        else:
            self.stats["unknown_type_names"].append(search)

        return type_name, py_import
