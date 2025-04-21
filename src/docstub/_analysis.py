"""Collect type information."""

import builtins
import collections.abc
import json
import logging
import re
import typing
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

    # docstub: off
    import_name: str | None = None
    import_path: str | None = None
    import_alias: str | None = None
    builtin_name: str | None = None
    # docstub: on

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

    def __repr__(self) -> str:
        if self.builtin_name:
            info = f"{self.target} (builtin)"
        else:
            info = f"{self.format_import()!r}"
        out = f"<{type(self).__name__} {info}>"
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


def _builtin_imports():
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


def _typing_imports():
    """Return known imports for public types in the `typing` module.

    Returns
    -------
    known_imports : dict[str, KnownImport]
    """
    known_imports = {}
    for name in typing.__all__:
        if name.startswith("_"):
            continue
        value = getattr(typing, name)
        if not _is_type(value):
            continue
        known_imports[name] = KnownImport.one_from_config(name, info={"from": "typing"})
    return known_imports


def _collections_abc_imports():
    """Return known imports for public types in the `collections.abc` module.

    Returns
    -------
    known_imports : dict[str, KnownImport]
    """
    known_imports = {}
    for name in collections.abc.__all__:
        if name.startswith("_"):
            continue
        value = getattr(collections.abc, name)
        if not _is_type(value):
            continue
        known_imports[name] = KnownImport.one_from_config(
            name, info={"from": "collections.abc"}
        )
    return known_imports


def common_known_imports():
    """Return known imports for commonly supported types.

    This includes builtin types, and types from the `typing` or
    `collections.abc` module.

    Returns
    -------
    known_imports : dict[str, KnownImport]
    """
    known_imports = _builtin_imports()
    known_imports |= _typing_imports()
    known_imports |= _collections_abc_imports()  # Overrides containers from typing
    return known_imports


class TypeCollector(cst.CSTVisitor):
    """Collect types from a given Python file.

    Examples
    --------
    >>> types = TypeCollector.collect(__file__)
    >>> types[f"{__name__}.TypeCollector"]
    <KnownImport 'from docstub._analysis import TypeCollector'>
    """

    class ImportSerializer:
        """Implements the `FuncSerializer` protocol to cache `TypeCollector.collect`."""

        suffix = ".json"
        encoding = "utf-8"

        def hash_args(self, path: Path) -> str:
            """Compute a unique hash from the path passed to `TypeCollector.collect`."""
            key = pyfile_checksum(path)
            return key

        def serialize(self, data: dict[str, KnownImport]) -> bytes:
            """Serialize results from `TypeCollector.collect`."""
            primitives = {qualname: asdict(imp) for qualname, imp in data.items()}
            raw = json.dumps(primitives, separators=(",", ":")).encode(self.encoding)
            return raw

        def deserialize(self, raw: bytes) -> dict[str, KnownImport]:
            """Deserialize results from `TypeCollector.collect`."""
            primitives = json.loads(raw.decode(self.encoding))
            data = {qualname: KnownImport(**kw) for qualname, kw in primitives.items()}
            return data

    @classmethod
    def collect(cls, file):
        """Collect importable type annotations in given file.

        Parameters
        ----------
        file : Path

        Returns
        -------
        collected : dict[str, KnownImport]
        """
        file = Path(file)
        with file.open("r") as fo:
            source = fo.read()

        tree = cst.parse_module(source)
        collector = cls(module_name=module_name_from_path(file))
        tree.visit(collector)
        return collector.known_imports

    def __init__(self, *, module_name):
        """Initialize type collector.

        Parameters
        ----------
        module_name : str
        """
        self.module_name = module_name
        self._stack = []
        self.known_imports = {}

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

    def _collect_type_annotation(self, stack):
        """Collect an importable type annotation.

        Parameters
        ----------
        stack : Iterable[str]
            A list of names that form the path to the collected type.
        """
        qualname = ".".join([self.module_name, *stack])
        known_import = KnownImport(import_path=self.module_name, import_name=stack[0])
        self.known_imports[qualname] = known_import


class TypesDatabase:
    """A static database of collected types usable as an annotation.

    Attributes
    ----------
    current_source : Path | None
    source_pkgs : list[Path]
    known_imports : dict[str, KnownImport]
    stats : dict[str, Any]

    Examples
    --------
    >>> from docstub._analysis import TypesDatabase, common_known_imports
    >>> db = TypesDatabase(known_imports=common_known_imports())
    >>> db.query("Any")
    ('Any', <KnownImport 'from typing import Any'>)
    """

    def __init__(
        self,
        *,
        source_pkgs=None,
        known_imports=None,
    ):
        """
        Parameters
        ----------
        source_pkgs : list[Path], optional
        known_imports : dict[str, KnownImport], optional
            If not provided, defaults to imports returned by
            :func:`common_known_imports`.
        """
        if source_pkgs is None:
            source_pkgs = []
        if known_imports is None:
            known_imports = common_known_imports()

        self.current_source = None
        self.source_pkgs = source_pkgs

        self.known_imports = known_imports

        self.stats = {
            "successful_queries": 0,
            "unknown_doctypes": [],
        }

    def query(self, search_name):
        """Search for a known annotation name.

        Parameters
        ----------
        search_name : str

        Returns
        -------
        annotation_name : str | None
            If it was found, the name of the annotation that matches the `known_import`.
        known_import : KnownImport | None
            If it was found, import information matching the `annotation_name`.
        """
        annotation_name = None
        known_import = None

        if search_name.startswith("~."):
            # Sphinx like matching with abbreviated name
            pattern = search_name.replace(".", r"\.")
            pattern = pattern.replace("~", ".*")
            regex = re.compile(pattern + "$")
            # Might be slow, but works for now
            matches = {
                key: value
                for key, value in self.known_imports.items()
                if regex.match(key)
            }
            if len(matches) > 1:
                shortest_key = sorted(matches.keys(), key=lambda x: len(x))[0]
                known_import = matches[shortest_key]
                annotation_name = shortest_key
                logger.warning(
                    "%r in %s matches multiple types %r, using %r",
                    search_name,
                    self.current_source,
                    matches.keys(),
                    shortest_key,
                )
            elif len(matches) == 1:
                annotation_name, known_import = matches.popitem()
            else:
                search_name = search_name[2:]
                logger.debug(
                    "couldn't match %r in %s", search_name, self.current_source
                )

        if known_import is None and self.current_source:
            # Try scope of current module
            module_name = module_name_from_path(self.current_source)
            try_qualname = f"{module_name}.{search_name}"
            known_import = self.known_imports.get(try_qualname)
            if known_import:
                annotation_name = search_name

        if known_import is None:
            # Try a subset of the qualname (first 'a.b.c', then 'a.b' and 'a')
            for partial_qualname in reversed(accumulate_qualname(search_name)):
                known_import = self.known_imports.get(partial_qualname)
                if known_import:
                    annotation_name = search_name
                    break

        if (
            known_import is not None
            and annotation_name is not None
            and annotation_name != known_import.target
            and not annotation_name.startswith(known_import.target)
        ):
            # Ensure that the annotation matches the import target
            annotation_name = annotation_name[
                annotation_name.find(known_import.target) :
            ]

        if annotation_name is not None:
            self.stats["successful_queries"] += 1
        else:
            self.stats["unknown_doctypes"].append(search_name)

        return annotation_name, known_import

    def __repr__(self) -> str:
        repr = f"{type(self).__name__}({self.source_pkgs})"
        return repr
