"""Collect type information."""

import builtins
import importlib
import json
import logging
import re
from dataclasses import asdict, dataclass, field
from functools import cache
from pathlib import Path
from typing import Self

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


class Node:
    def __init__(self, name):
        self.name = name
        self._parent = None
        self._children = []

    @property
    def parent(self):
        return self._parent

    @property
    def children(self):
        return self._children.copy()

    @property
    def is_leaf(self):
        return not self._children

    @property
    def fullname(self):
        names = [node.name for node in self.walk_up()][::-1]
        return ".".join(names)

    def add_child(self, child):
        assert child.parent is None
        child._parent = self
        self._children.append(child)

    def walk_down(self):
        yield self
        for child in self._children:
            yield from child.walk_down()

    def walk_up(self):
        current = self
        while current.parent is not None:
            yield current
            current = current.parent

    def __repr__(self):
        return f"{type(self).__name__}({self.name!r})"


class Tree(Node):
    def __init__(self):
        super().__init__(name=None)

    def add_child(self, child):
        if not isinstance(child, ModuleNode):
            raise TypeError("expected new child to by a module")
        return super().add_child(child)

    def get(self):


class ModuleNode(Node):

    def __init__(self, name, file_path):
        super().__init__(name=name)
        self.file_path = file_path


class _InModuleNode(Node):
    pass


class ClassNode(_InModuleNode):
    pass


class TypeAliasNode(_InModuleNode):
    pass


class ImportFromNode(_InModuleNode):
    pass


class NodeCollector(cst.CSTVisitor):
    """Collect types from a given Python file.

    Examples
    --------
    >>> types = NodeCollector.collect(__file__)
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
    def collect(cls, file_path):
        """Collect importable type annotations in given file.

        Parameters
        ----------
        file : Path

        Returns
        -------
        collected : dict[str, KnownImport]
        """
        file_path = Path(file_path)
        with file_path.open("r") as fo:
            source = fo.read()

        tree = cst.parse_module(source)
        collector = cls(file_path=file_path)
        tree.visit(collector)
        return collector._root_node

    def __init__(self, *, file_path):
        """Initialize type collector.

        Parameters
        ----------
        module_name : str
        """
        assert "." not in file_path.stem
        self._root_node = ModuleNode(name=file_path.stem, file_path=file_path)
        self._current_node = self._root_node

    def visit_ClassDef(self, node: cst.ClassDef) -> bool:
        node = ClassNode(name=node.name.value)
        self._current_node.add_child(node)
        self._current_node = node
        return True

    def leave_ClassDef(self, original_node: cst.ClassDef) -> None:
        self._current_node = self._current_node.parent

    def visit_FunctionDef(self, node: cst.FunctionDef) -> bool:
        return False

    def visit_TypeAlias(self, node: cst.TypeAlias) -> bool:
        """Collect type alias with 3.12 syntax."""
        node = TypeAliasNode(name=node.name.value)
        self._current_node.add_child(node)
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
            node = Node(name=names[0].value)
            self._current_node.add_child(node)
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

            node = ImportFromNode(name=name)
            self._current_node.add_child(node)


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
    types : dict[str, KnownImport]
    type_prefixes : dict[str, KnownImport]
    type_nicknames : dict[str, str]
    successful_queries : int
    unknown_qualnames : list
    current_module : Path | None

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
        self.types = types or common_known_types()
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
        type_name : str | None
        type_origin : KnownImport | None
        """
        type_name = None
        type_origin = None

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
                type_origin = matches[shortest_key]
                type_name = shortest_key
                logger.warning(
                    "%r in %s matches multiple types %r, using %r",
                    search_name,
                    self.current_module or "<file not known>",
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
                    self.current_module or "<file not known>",
                )

        # Replace alias
        search_name = self.type_nicknames.get(search_name, search_name)

        if type_origin is None and self.current_module:
            # Try scope of current module
            module_name = module_name_from_path(self.current_module)
            try_qualname = f"{module_name}.{search_name}"
            type_origin = self.types.get(try_qualname)
            if type_origin:
                type_name = search_name

        if type_origin is None and search_name in self.types:
            type_name = search_name
            type_origin = self.types[search_name]

        if type_origin is None:
            # Try a subset of the qualname (first 'a.b.c', then 'a.b' and 'a')
            for partial_qualname in reversed(accumulate_qualname(search_name)):
                type_origin = self.type_prefixes.get(partial_qualname)
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
