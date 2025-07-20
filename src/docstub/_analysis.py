"""Collect type information."""

import builtins
import importlib
import json
import logging
import re
import dataclasses as dc
from itertools import pairwise
from functools import cache
from pathlib import Path
from typing import Self, ClassVar

import libcst as cst
import libcst.matchers as cstm

from ._utils import accumulate_qualname, module_name_from_path, pyfile_checksum
from . import __version__

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


@dc.dataclass(slots=True, frozen=True)
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
            info = f"{self.target} (builtin)"
        else:
            info = f"{self.format_import()!r}"
        out = f"<{type(self).__name__} {info}>"
        return out

    def __str__(self) -> str:
        out = self.format_import()
        return out


@dc.dataclass(slots=True, kw_only=True)
class PyNode:
    _TYPE_KINDS: ClassVar[set[str]] = {
        "builtin",
        "class",
        "type_alias",
        "ann_assign",
        "import_from",
        "generic_type",
    }
    _KINDS: ClassVar[set[str]] = {"module"} | _TYPE_KINDS

    name: str
    kind: str
    loc: str | None = None
    parent: Self | None = None
    children: list[Self] = dc.field(default_factory=list)

    @property
    def is_leaf(self):
        return not self.children

    @property
    def fullname(self):
        names = [node.name for node in self.walk_parents()][::-1]
        return ".".join(names + [self.name])

    @property
    def is_type(self):
        return self.kind in self._TYPE_KINDS

    @property
    def import_statement(self):
        module = []
        qualname = [self.name]
        for parent in self.walk_parents():
            if parent.kind == "module":
                module.insert(0, parent.name)
            else:
                qualname.insert(0, parent.name)

        if module:
            return f"from {'.'.join(module)} import {'.'.join(qualname)}"
        else:
            return None

    def add_child(self, child):
        assert child.parent is None
        child.parent = self
        self.children.append(child)

    def _walk_tree(self, names=()):
        names = names + (self.name,)
        yield names, self
        for child in self.children:
            yield from child._walk_tree(names)

    def walk_tree(self):
        yield from self._walk_tree()

    def walk_parents(self):
        current = self.parent
        while current is not None:
            yield current
            current = current.parent

    def serialize_tree(self):
        raw = {field.name: getattr(self, field.name) for field in dc.fields(self)}
        del raw["parent"]
        raw["children"] = [child.serialize_tree() for child in self.children]
        return raw

    @classmethod
    def from_serialized_tree(cls, primitives):
        self = cls(**primitives)
        if self.parent:
            self.parent = cls.from_serialized_tree(self.parent)
        self.children = [cls.from_serialized_tree(child) for child in self.children]
        return self

    def __repr__(self):
        return f"{type(self).__name__}({self.name!r}, kind={self.kind!r})"

    def __post_init__(self):
        unsupported_kind = {self.kind} - self._KINDS
        if unsupported_kind:
            msg = f"unsupported kind {unsupported_kind}, supported are {self._KINDS}"
            raise ValueError(msg)


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
    """Builtin types in the current runtime.

    Returns
    -------
    types : dict[str, PyNode]
    """
    builtins_names = set(dir(builtins))

    types = {}
    for name in builtins_names:
        if name.startswith("_"):
            continue
        value = getattr(builtins, name)
        if not _is_type(value):
            continue
        types[name] = PyNode(name=name, kind="builtin")

    return types


def _runtime_types_in_module(module_name):
    module = importlib.import_module(module_name)

    modules = [PyNode(name=name, kind="module") for name in module_name.split(".")]
    for parent, child in pairwise(modules):
        parent.add_child(child)

    types = {}
    for name in module.__all__:
        if name.startswith("_"):
            continue
        value = getattr(module, name)
        if not _is_type(value):
            continue

        pynode = PyNode(name=name, kind="generic_type")
        modules[-1].add_child(pynode)
        types[pynode.fullname] = pynode

    return types


def common_types_nicknames():
    """Return known imports for commonly supported types.

    This includes builtin types, and types from the `typing` or
    `collections.abc` module.

    Returns
    -------
    types : list[PyNode]
    type_nicknames : dict[str, str]

    Examples
    --------
    >>> types = common_known_types()
    >>> types["str"]
    PyNode('str', kind='builtin')
    >>> types["Iterable"]
    PyNode('Iterable', kind='generic_type')
    >>> types["Iterable"].fullname
    'collections.abc.Iterable'
    >>> types["collections.abc.Iterable"]
    PyNode('Iterable', kind='generic_type')
    """
    pynodes = _builtin_types()
    pynodes |= _runtime_types_in_module("typing")
    collections_abc = _runtime_types_in_module("collections.abc")
    pynodes |= collections_abc

    type_nicknames = {node.name: fullname for fullname, node in collections_abc.items()}

    return pynodes, type_nicknames


class PythonCollector(cst.CSTVisitor):
    """Collect types from a given Python file.

    Examples
    --------
    >>> types = PythonCollector.collect(__file__)
    >>> types[f"{__name__}.TypeCollector"]
    <KnownImport 'from docstub._analysis import TypeCollector'>
    """

    METADATA_DEPENDENCIES = (cst.metadata.PositionProvider,)

    class ImportSerializer:
        """Implements the `FuncSerializer` protocol to cache `TypeCollector.collect`."""

        suffix = ".json"
        encoding = "utf-8"

        def hash_args(self, path: Path) -> str:
            """Compute a unique hash from the path passed to `TypeCollector.collect`."""
            key = pyfile_checksum(path, salt=__version__)
            return key

        def serialize(self, pynode: PyNode) -> bytes:
            """Serialize results from `TypeCollector.collect`."""
            primitives = pynode.serialize_tree()
            raw = json.dumps(primitives, separators=(",", ":")).encode(self.encoding)
            return raw

        def deserialize(self, raw: bytes) -> PyNode:
            """Deserialize results from `TypeCollector.collect`."""
            primitives = json.loads(raw.decode(self.encoding))
            pynode = PyNode.from_serialized_tree(primitives)
            return pynode

    @classmethod
    def collect(cls, file_path):
        """Collect importable type annotations in given file.

        Parameters
        ----------
        file_path : Path

        Returns
        -------
        module_tree : PyNode
        """
        file_path = Path(file_path)
        with file_path.open("r") as fo:
            source = fo.read()

        tree = cst.parse_module(source)
        meta_tree = cst.metadata.MetadataWrapper(tree)
        collector = cls(file_path=file_path)
        meta_tree.visit(collector)

        return collector._root_pynode

    def __init__(self, *, file_path):
        """Initialize type collector.

        Parameters
        ----------
        module_name : str
        """
        full_module_name = module_name_from_path(file_path)
        current_module, *parent_modules = full_module_name.split(".")[::-1]

        self._file_path = file_path
        self._root_pynode = PyNode(
            name=current_module, kind="module", loc=str(file_path)
        )
        self._current_pynode = self._root_pynode

        for name in parent_modules:
            # TODO set location for parent modules too
            parent = PyNode(name=name, kind="module")
            parent.add_child(self._root_pynode)
            self._root_pynode = parent

    def _get_loc(self, node):
        pos = self.get_metadata(cst.metadata.PositionProvider, node).start
        loc = f"{self._file_path}:{pos.line}:{pos.column}"
        return loc

    def visit_ClassDef(self, node: cst.ClassDef) -> bool:
        pynode = PyNode(name=node.name.value, kind="class", loc=self._get_loc(node))
        self._current_pynode.add_child(pynode)
        self._current_pynode = pynode
        return True

    def leave_ClassDef(self, original_node: cst.ClassDef) -> None:
        self._current_pynode = self._current_pynode.parent

    def visit_FunctionDef(self, node: cst.FunctionDef) -> bool:
        return False

    def visit_TypeAlias(self, node: cst.TypeAlias) -> bool:
        """Collect type alias with 3.12 syntax."""
        pynode = PyNode(
            name=node.name.value, kind="type_alias", loc=self._get_loc(node)
        )
        self._current_pynode.add_child(pynode)
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
            pynode = PyNode(
                name=names[0].value, kind="ann_assign", loc=self._get_loc(node)
            )
            self._current_pynode.add_child(pynode)
        return False

    def visit_ImportFrom(self, node: cst.ImportFrom) -> None:
        """Collect "from import" targets as usable types within each module."""
        for import_alias in node.names:
            if cstm.matches(import_alias, cstm.ImportStar()):
                continue
            name = import_alias.evaluated_alias
            if name is None:
                name = import_alias.evaluated_name
            assert isinstance(name, str)

            pynode = PyNode(name=name, kind="import_from", loc=self._get_loc(node))
            self._current_pynode.add_child(pynode)


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


class TypeMatcher:
    """Match strings to collected type information.

    Attributes
    ----------
    types : dict[str, PyNode]
    type_prefixes : dict[str, KnownImport]
    type_nicknames : dict[str, str]
    successful_queries : int
    unknown_qualnames : list
    current_module : Path | None

    Examples
    --------
    >>> from docstub._analysis import TypeMatcher
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
        self.types = types or {}
        self.type_prefixes = type_prefixes or {}
        self.type_nicknames = type_nicknames or {}
        self.successful_queries = 0
        self.unknown_qualnames = []
        self.current_module = None

    def match(self, search_name):
        """Search for a known annotation name.

        Parameters
        ----------
        search_name : str
        current_module : Path, optional

        Returns
        -------
        type : pynode | None
        """
        pynode = None

        if search_name.startswith("~."):
            # Sphinx like matching with abbreviated name
            pattern = search_name.replace(".", r"\.")
            pattern = pattern.replace("~", ".*")
            regex = re.compile(pattern + "$")
            # Might be slow, but works for now
            matches = {
                key: value for key, value in self.types.items() if regex.match(key)
            }
            if len(matches) > 1:
                shortest_key = sorted(matches.keys(), key=lambda x: len(x))[0]
                pynode = matches[shortest_key]
                logger.warning(
                    "%r in %s matches multiple types %r, using %r",
                    search_name,
                    self.current_module or "<file not known>",
                    matches.keys(),
                    shortest_key,
                )
            elif len(matches) == 1:
                _, pynode = matches.popitem()
            else:
                search_name = search_name[2:]
                logger.debug(
                    "couldn't match %r in %s",
                    search_name,
                    self.current_module or "<file not known>",
                )

        # Replace alias
        search_name = self.type_nicknames.get(search_name, search_name)

        if pynode is None and self.current_module:
            # Try scope of current module
            module_name = module_name_from_path(self.current_module)
            try_qualname = f"{module_name}.{search_name}"
            pynode = self.types.get(try_qualname)

        if pynode is None and search_name in self.types:
            pynode = self.types[search_name]

        if pynode is None:
            # Try a subset of the qualname (first 'a.b.c', then 'a.b' and 'a')
            for partial_qualname in reversed(accumulate_qualname(search_name)):
                pynode = self.type_prefixes.get(partial_qualname)
                if pynode:
                    break

        if pynode is not None:
            self.successful_queries += 1
        else:
            self.unknown_qualnames.append(search_name)

        return pynode
