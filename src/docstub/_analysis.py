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

logger = logging.getLogger(__name__)


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
class KnownImport:
    """Import information associated with a single known type annotation.

    Attributes
    ----------
    import_path
        Dotted names after "from".
    import_name
        Dotted names after "import".
    import_alias
        Name (without ".") after "as".
    builtin_name
        Names an object that's builtin and doesn't need an import.

    Examples
    --------
    >>> KnownImport(import_path="numpy", import_name="uint8", import_alias="ui8")
    <KnownImport 'from numpy import uint8 as ui8'>
    """

    import_name: str | None = None
    import_path: str | None = None
    import_alias: str | None = None
    builtin_name: str | None = None

    @classmethod
    @cache
    def typeshed_Incomplete(cls):
        """Create import corresponding to ``from _typeshed import Incomplete``.

        This type is not actually available at runtime and only intended to be
        used in stub files [1]_.

        Returns
        -------
        import : KnownImport
            The import corresponding to ``from _typeshed import Incomplete``.

        References
        ----------
        .. [1] https://typing.readthedocs.io/en/latest/guides/writing_stubs.html#incomplete-stubs
        """
        import_ = cls(import_path="_typeshed", import_name="Incomplete")
        return import_

    @classmethod
    def one_from_config(cls, name, *, info):
        """Create one KnownImport from the configuration format.

        Parameters
        ----------
        name : str
        info : dict[{"from", "import", "as", "is_builtin"}, str]

        Returns
        -------
        TypeImport : Self
        """
        assert not (info.keys() - {"from", "import", "as", "is_builtin"})

        if info.get("is_builtin"):
            known_import = cls(builtin_name=name)
        else:
            import_name = name
            if "import" in info:
                import_name = info["import"]

            known_import = cls(
                import_name=import_name,
                import_path=info.get("from"),
                import_alias=info.get("as"),
            )
            if not name.startswith(known_import.target):
                raise ValueError(
                    f"{name!r} doesn't start with {known_import.target!r}",
                )

        return known_import

    @classmethod
    def many_from_config(cls, mapping):
        """Create many KnownImports from the configuration format.

        Parameters
        ----------
        mapping : dict[str, dict[{"from", "import", "as", "is_builtin"}, str]]

        Returns
        -------
        known_imports : dict[str, Self]
        """
        known_imports = {
            name: cls.one_from_config(name, info=info) for name, info in mapping.items()
        }
        return known_imports

    def format_import(self, relative_to=None):
        if self.builtin_name:
            msg = "cannot import builtin"
            raise RuntimeError(msg)
        out = f"import {self.import_name}"

        import_path = self.import_path
        if import_path:
            if relative_to:
                shared = _shared_leading_qualname(relative_to, import_path)
                if shared == import_path:
                    import_path = "."
                else:
                    import_path = self.import_path.replace(shared, "")

            out = f"from {import_path} {out}"
        if self.import_alias:
            out = f"{out} as {self.import_alias}"
        return out

    @property
    def target(self) -> str:
        if self.import_alias:
            out = self.import_alias
        elif self.import_name:
            out = self.import_name
        elif self.builtin_name:
            out = self.builtin_name
        else:
            raise RuntimeError("cannot determine import target")
        return out

    @property
    def has_import(self):
        return self.builtin_name is None

    def __post_init__(self):
        if self.builtin_name is not None:
            if (
                self.import_name is not None
                or self.import_alias is not None
                or self.import_path is not None
            ):
                raise ValueError("builtin cannot contain import information")
        elif self.import_name is None:
            raise ValueError("non builtin must at least define an `import_name`")
        if self.import_alias is not None and "." in self.import_alias:
            raise ValueError("`import_alias` can't contain a '.'")

    def __repr__(self) -> str:
        if self.builtin_name:
            kwargs = f"builtin_name={self.builtin_name!r}"
        else:
            kwargs = (
                f"import_path={self.import_path!r}, "
                f"import_name={self.import_name!r}, "
                f"import_alias={self.import_alias!r}"
            )
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
    """Return known imports for all builtins (in the current runtime).

    Returns
    -------
    known_imports : dict[str, KnownImport]
    """
    known_builtins = set(dir(builtins))

    known_imports = {}
    for name in known_builtins:
        if name.startswith("_"):
            continue
        value = getattr(builtins, name)
        if not _is_type(value):
            continue
        known_imports[name] = KnownImport(builtin_name=name)

    return known_imports


def _runtime_types_in_module(module_name):
    module = importlib.import_module(module_name)
    types = {}
    for name in module.__all__:
        if name.startswith("_"):
            continue
        value = getattr(module, name)
        if not _is_type(value):
            continue

        import_ = KnownImport(import_path=module_name, import_name=name)
        types[name] = import_
        types[f"{module_name}.{name}"] = import_

    return types


def common_known_types():
    """Return known imports for commonly supported types.

    This includes builtin types, and types from the `typing` or
    `collections.abc` module.

    Returns
    -------
    known_imports : dict[str, KnownImport]

    Examples
    --------
    >>> types = common_known_types()
    >>> types["str"]
    <KnownImport str (builtin)>
    >>> types["Iterable"]
    <KnownImport 'from collections.abc import Iterable'>
    >>> types["collections.abc.Iterable"]
    <KnownImport 'from collections.abc import Iterable'>
    """
    known_imports = _builtin_types()
    known_imports |= _runtime_types_in_module("typing")
    # Overrides containers from typing
    known_imports |= _runtime_types_in_module("collections.abc")
    return known_imports


@dataclass(slots=True, kw_only=True)
class TypeCollectionResult:
    types: dict[str, KnownImport]
    type_prefixes: dict[str, KnownImport]

    @classmethod
    def serialize(cls, result):
        pass

    @classmethod
    def deserialize(cls, result):
        pass


class TypeCollector(cst.CSTVisitor):
    """Collect types from a given Python file.

    Examples
    --------
    >>> types, prefixes = TypeCollector.collect(__file__)
    >>> types[f"{__name__}.TypeCollector"]
    <KnownImport 'from docstub._analysis import TypeCollector'>
    >>> prefixes["logging"]
    <KnownImport 'import logging'>
    """

    class ImportSerializer:
        """Implements the `FuncSerializer` protocol to cache `TypeCollector.collect`."""

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
            data : tuple[dict[str, KnownImport], dict[str, KnownImport]]

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
            types : dict[str, KnownImport]
            type_prefixes : dict[str, KnownImport]
            """
            primitives = json.loads(raw.decode(self.encoding))

            def deserialize_table(table):
                return {key: KnownImport(**kw) for key, kw in table.items()}

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
        types : dict[str, KnownImport]
        type_prefixes : dict[str, KnownImport]
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
                known_import = KnownImport(
                    import_path=".".join(from_names), import_name=name
                )
                self.types[key] = known_import

            scoped_import = KnownImport(builtin_name=asname or name)
            self.types[f"{self.module_name}:{asname or name}"] = scoped_import

        return False

    def visit_Import(self, node: cst.Import) -> bool:
        for import_alias in node.names:
            asname = import_alias.evaluated_alias
            name = import_alias.evaluated_name
            target = asname or name

            known_import = KnownImport(builtin_name=asname or name)
            self.type_prefixes[f"{self.module_name}:{target}"] = known_import

        return False

    def _collect_type_annotation(self, stack):
        """Collect an importable type annotation.

        Parameters
        ----------
        stack : Iterable[str]
            A list of names that form the path to the collected type.
        """
        qualname = ".".join([self.module_name, *stack])
        known_import = KnownImport(import_path=self.module_name, import_name=stack[0])
        self.types[qualname] = known_import


class TypeMatcher:
    """Match strings to collected type information.

    Attributes
    ----------
    types : dict[str, KnownImport]
    type_prefixes : dict[str, KnownImport]
    type_nicknames : dict[str, str]
    successful_queries : int
    unknown_qualnames : list
    current_file : Path | None

    Examples
    --------
    >>> from docstub._analysis import TypeMatcher, common_known_types
    >>> db = TypeMatcher()
    >>> db.match("Any")
    ('Any', <KnownImport 'from typing import Any'>)
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
        types : dict[str, KnownImport]
        type_prefixes : dict[str, KnownImport]
        type_nicknames : dict[str, str]
        """

        self.types = common_known_types() | (types or {})
        self.type_prefixes = type_prefixes or {}
        self.type_nicknames = type_nicknames or {}
        self.successful_queries = 0
        self.unknown_qualnames = []

        self.current_file = None

    def match(self, search_name):
        """Search for a known annotation name.

        Parameters
        ----------
        search_name : str
        current_module : Path, optional

        Returns
        -------
        type_name : str | None
        type_origin : KnownImport | None
        """
        type_name = None
        type_origin = None

        module = module_name_from_path(self.current_file) if self.current_file else None

        if search_name.startswith("~."):
            # Sphinx like matching with abbreviated name
            pattern = search_name.replace(".", r"\.")
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
                type_origin = matches[shortest_key]
                type_name = shortest_key
                logger.warning(
                    "%r in %s matches multiple types %r, using %r",
                    search_name,
                    self.current_file or "<file not known>",
                    matches.keys(),
                    shortest_key,
                )
            elif len(matches) == 1:
                type_name, type_origin = matches.popitem()
            else:
                search_name = search_name[2:]
                logger.debug(
                    "couldn't match %r in %s",
                    search_name,
                    self.current_file or "<file not known>",
                )

        # Replace alias
        search_name = self.type_nicknames.get(search_name, search_name)

        if type_origin is None and module:
            # Look for matching type in current module
            type_origin = self.types.get(f"{module}:{search_name}")
            type_origin = self.types.get(f"{module}.{search_name}", type_origin)
            if type_origin:
                type_name = search_name

        if type_origin is None and search_name in self.types:
            type_name = search_name
            type_origin = self.types[search_name]

        if type_origin is None:
            # Try a subset of the qualname (first 'a.b.c', then 'a.b' and 'a')
            for partial_qualname in reversed(accumulate_qualname(search_name)):
                type_origin = self.type_prefixes.get(f"{module}:{partial_qualname}")
                type_origin = self.type_prefixes.get(partial_qualname, type_origin)
                if type_origin:
                    type_name = search_name
                    break

        if (
            type_origin is not None
            and type_name is not None
            and type_name != type_origin.target
            and not type_name.startswith(type_origin.target)
        ):
            # Ensure that the annotation matches the import target
            type_name = type_name[type_name.find(type_origin.target) :]

        if type_name is not None:
            self.successful_queries += 1
        else:
            self.unknown_qualnames.append(search_name)

        return type_name, type_origin
