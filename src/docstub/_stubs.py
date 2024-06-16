"""Transform Python source files to typed stub files.

"""

import enum
import logging
from dataclasses import dataclass
from pathlib import Path

import libcst as cst
import libcst.matchers as cstm

from ._docstrings import collect_pytypes

logger = logging.getLogger(__name__)


class PackageFile(Path):
    """File in a Python package."""

    def __init__(self, *args, package_root):
        """
        Parameters
        ----------
        args : tuple[Any, ...]
        package_root : Path
        """
        self.package_root = package_root
        super().__init__(*args)
        if self.is_dir():
            raise ValueError("mustn't be a directory")
        if not self.is_relative_to(self.package_root):
            raise ValueError("path must be relative to package_root")

    @property
    def import_path(self):
        """
        Returns
        -------
        str
        """
        relative_to_root = self.relative_to(self.package_root)
        parts = relative_to_root.with_suffix("").parts
        parts = (self.package_root.name, *parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        import_name = ".".join(parts)
        return import_name

    def with_segments(self, *args):
        return Path(*args)


def _is_python_package(path):
    """
    Parameters
    ----------
    path : Path

    Returns
    -------
    is_package : bool
    """
    is_package = (path / "__init__.py").is_file() or (path / "__init__.pyi").is_file()
    return is_package


def walk_source(root_dir):
    """Iterate modules in a Python package and its target stub files.

    Parameters
    ----------
    root_dir : Path
        Root directory of a Python package.
    target_dir : Path
        Root directory in which a matching stub package will be created.

    Yields
    ------
    source_path : PackageFile
        Either a Python file or a stub file that takes precedence.

    Notes
    -----
    Files starting with "test_" are skipped entirely for now.
    """
    queue = [root_dir]
    while queue:
        path = queue.pop(0)

        if path.is_dir():
            if _is_python_package(path):
                queue.extend(path.iterdir())
            else:
                logger.debug("skipping directory %s", path)
            continue

        assert path.is_file()

        suffix = path.suffix.lower()
        if suffix not in {".py", ".pyi"}:
            continue
        if suffix == ".py" and path.with_suffix(".pyi").exists():
            continue  # Stub file already exists and takes precedence

        python_file = PackageFile(path, package_root=root_dir)
        yield python_file


def walk_source_and_targets(root_dir, target_dir):
    """Iterate modules in a Python package and its target stub files.

    Parameters
    ----------
    root_dir : Path
        Root directory of a Python package.
    target_dir : Path
        Root directory in which a matching stub package will be created.

    Returns
    -------
    source_path : PackageFile
        Either a Python file or a stub file that takes precedence.
    stub_path : PackageFile
        Target stub file.

    Notes
    -----
    Files starting with "test_" are skipped entirely for now.
    """
    for source_path in walk_source(root_dir):
        stub_path = target_dir / source_path.with_suffix(".pyi").relative_to(root_dir)
        stub_path = PackageFile(stub_path, package_root=target_dir)
        yield source_path, stub_path


def try_format_stub(stub: str) -> str:
    """Try to format a stub file with isort and black if available."""
    try:
        import isort

        stub = isort.code(stub)
    except ImportError:
        logger.warning("isort is not available, couldn't sort imports")
    try:
        import black

        stub = black.format_str(stub, mode=black.Mode(is_pyi=True))
    except ImportError:
        logger.warning("black is not available, couldn't format stubs")
    return stub


class FuncType(enum.Enum):
    MODULE = enum.auto()
    CLASS = enum.auto()
    FUNC = enum.auto()
    METHOD = enum.auto()
    CLASSMETHOD = enum.auto()
    STATICMETHOD = enum.auto()


@dataclass(slots=True, frozen=True)
class _Scope:
    """"""

    type: FuncType
    node: cst.CSTNode = None

    @property
    def has_self_or_cls(self):
        return self.type in {FuncType.METHOD, FuncType.CLASSMETHOD}

    @property
    def is_method(self):
        return self.type in {
            FuncType.METHOD,
            FuncType.CLASSMETHOD,
            FuncType.STATICMETHOD,
        }

    @property
    def is_class_init(self):
        out = self.is_method and self.node.name.value == "__init__"
        return out


class Py2StubTransformer(cst.CSTTransformer):
    """Transform syntax tree of a Python file into the tree of a stub file.

    Attributes
    ----------
    inspector : ~._analysis.StaticInspector
    """

    # Equivalent to ` ...`, to replace the body of callables with
    _body_replacement = cst.SimpleStatementSuite(
        leading_whitespace=cst.SimpleWhitespace(value=" "),
        body=[cst.Expr(value=cst.Ellipsis())],
    )
    _Annotation_Any = cst.Annotation(cst.Name("Any"))
    _Annotation_None = cst.Annotation(cst.Name("None"))

    def __init__(self, *, inspector):
        """
        Parameters
        ----------
        inspector : ~._analysis.StaticInspector
        """
        self.inspector = inspector
        # Relevant docstring for the current context
        self._scope_stack = None  # Entered module, class or function scopes
        self._pytypes_stack = None  # Collected pytypes for each stack
        self._required_imports = None  # Collect imports for used types
        self._current_module = None

    def python_to_stub(self, source, *, module_path=None):
        """Convert Python source code to stub-file ready code.

        Parameters
        ----------
        source  : str
        module_path : PackageFile, optional
            The location of the source that is transformed into a stub file.
            If given, used to enhance logging & error messages with more
            context information.

        Returns
        -------
        stub : str
        """
        try:
            self._scope_stack = []
            self._pytypes_stack = []
            self._required_imports = set()
            if module_path:
                self.inspector.current_source = module_path

            source_tree = cst.parse_module(source)
            stub_tree = source_tree.visit(self)
            stub = stub_tree.code
            stub = try_format_stub(stub)
            return stub
        finally:
            self._scope_stack = None
            self._pytypes_stack = None
            self._required_imports = None
            self.inspector.current_source = None

    def visit_ClassDef(self, node):
        """Collect pytypes from class docstring and add scope to stack.

        Parameters
        ----------
        node : cst.ClassDef

        Returns
        -------
        out : Literal[True]
        """
        self._scope_stack.append(_Scope(type=FuncType.CLASS, node=node))
        pytypes = self._pytypes_from_node(node)
        self._pytypes_stack.append(pytypes)
        return True

    def leave_ClassDef(self, original_node, updated_node):
        """Drop class scope from the stack.

        Parameters
        ----------
        original_node : cst.ClassDef
        updated_node : cst.ClassDef

        Returns
        -------
        updated_node : cst.ClassDef
        """
        self._scope_stack.pop()
        self._pytypes_stack.pop()
        return updated_node

    def visit_FunctionDef(self, node):
        """Collect pytypes from function docstring and add scope to stack.

        Parameters
        ----------
        node : cst.FunctionDef

        Returns
        -------
        out : Literal[True]
        """
        func_type = self._function_type(node)
        self._scope_stack.append(_Scope(type=func_type, node=node))
        pytypes = self._pytypes_from_node(node)
        self._pytypes_stack.append(pytypes)
        return True

    def leave_FunctionDef(self, original_node, updated_node):
        """Add type annotation for return to function.

        Parameters
        ----------
        original_node : cst.FunctionDef
        updated_node : cst.FunctionDef

        Returns
        -------
        updated_node : cst.FunctionDef
        """
        node_changes = {
            "body": self._body_replacement,
            "returns": self._Annotation_None,
        }

        pytypes = self._pytypes_stack.pop()
        if pytypes and pytypes.returns:
            assert pytypes.returns.value
            node_changes["returns"] = cst.Annotation(
                cst.parse_expression(pytypes.returns.value)
            )
            self._required_imports |= pytypes.returns.imports

        updated_node = updated_node.with_changes(**node_changes)
        self._scope_stack.pop()
        return updated_node

    def leave_Param(self, original_node, updated_node):
        """Add type annotation to parameter.

        Parameters
        ----------
        original_node : cst.Param
        updated_node : cst.Param

        Returns
        -------
        updated_node : cst.Param
        """
        node_changes = {}

        scope = self._scope_stack[-1]
        # Check if is first parameter of method or classmethod
        is_self_or_cls = (
            scope.node.params.children[0] is original_node and scope.has_self_or_cls
        )

        name = original_node.name.value
        pytypes = self._pytypes_stack[-1]
        if not pytypes and scope.is_class_init:
            pytypes = self._pytypes_stack[-2]
        if pytypes:
            pytype = pytypes.parameters.get(name)
            if pytype:
                annotation = cst.Annotation(cst.parse_expression(pytype.value))
                node_changes["annotation"] = annotation
                if pytype.imports:
                    self._required_imports |= pytype.imports

        # Potentially use "Any" except for first param in (class)methods
        elif not is_self_or_cls and updated_node.annotation is None:
            node_changes["annotation"] = self._Annotation_Any
            self._required_imports.add(self.inspector.query("Any"))

        if updated_node.default is not None:
            node_changes["default"] = cst.Ellipsis()

        if node_changes:
            updated_node = updated_node.with_changes(**node_changes)
        return updated_node

    def leave_Expr(self, original_node, updated_node):
        """Drop expression from stub file.

        Parameters
        ----------
        original_node : cst.Expr
        updated_node : cst.Expr

        Returns
        -------
        cst.RemovalSentinel
        """
        return cst.RemovalSentinel.REMOVE

    def leave_Comment(self, original_node, updated_node):
        """Drop comment from stub file.

        Parameters
        ----------
        original_node : cst.Comment
        updated_node : cst.Comment

        Returns
        -------
        cst.RemovalSentinel
        """
        return cst.RemovalSentinel.REMOVE

    def leave_Assign(self, original_node, updated_node):
        """Drop value of assign statements from stub files.

        Parameters
        ----------
        original_node : cst.Assign
        updated_node : cst.Assign

        Returns
        -------
        updated_node : cst.Assign
        """
        targets = cstm.findall(updated_node, cstm.AssignTarget())
        names_are__all__ = [
            name
            for target in targets
            for name in cstm.findall(target, cst.Name(value="__all__"))
        ]
        if not names_are__all__:
            # TODO replace with AnnAssign if possible / figure out assign type?
            updated_node = updated_node.with_changes(value=self._body_replacement)
        return updated_node

    def visit_Module(self, node):
        """Add module scope to stack.

        Parameters
        ----------
        node : cst.Module

        Returns
        -------
        Literal[True]
        """
        self._scope_stack.append(_Scope(type=FuncType.MODULE, node=node))
        pytypes = self._pytypes_from_node(node)
        self._pytypes_stack.append(pytypes)
        return True

    def leave_Module(self, original_node, updated_node):
        """Add required type imports to module

        Parameters
        ----------
        original_node : cst.Module
        updated_node : cst.Module

        Returns
        -------
        updated_node : cst.Module
        """
        current_module = self.inspector.current_source.import_path
        required_imports = [
            imp for imp in self._required_imports if imp.import_path != current_module
        ]
        import_nodes = self._parse_imports(
            required_imports, current_module=current_module
        )
        updated_node = updated_node.with_changes(body=import_nodes + updated_node.body)
        self._scope_stack.pop()
        self._pytypes_stack.pop()
        return updated_node

    def visit_Lambda(self, node):
        """Don't visit parameters fo lambda which can't have an annotation.

        Parameters
        ----------
        node : cst.Lambda

        Returns
        -------
        Literal[False]
        """
        return False

    def leave_Decorator(self, original_node, updated_node):
        """Drop decorators except for a few out of the SDL.

        Parameters
        ----------
        original_node : cst.Decorator
        updated_node : cst.Decorator

        Returns
        -------
        cst.Decorator | cst.RemovalSentinel
        """
        names = cstm.findall(original_node, cstm.Name())
        names = ".".join(name.value for name in names)

        allowlist = (
            "classmethod",
            "staticmethod",
            "property",
            ".setter",
            "abstractmethod",
            "dataclass",
            "coroutine",
        )
        out = cst.RemovalSentinel.REMOVE
        # TODO add decorators in typing module
        for allowed in allowlist:
            if allowed in names:
                out = updated_node
        return out

    @staticmethod
    def _parse_imports(imports, *, current_module=None):
        """Create nodes to include in the module tree from given imports.

        Parameters
        ----------
        imports : set[~.DocName]
        current_module : str, optional

        Returns
        -------
        import_nodes : tuple[cst.SimpleStatementLine, ...]
        """
        lines = {imp.format_import(relative_to=current_module) for imp in imports}
        import_nodes = tuple(cst.parse_statement(line) for line in lines)
        return import_nodes

    def _function_type(self, func_def):
        """Determine if a function is a method, property, staticmethod, ...

        Parameters
        ----------
        func_def : cst.FunctionDef

        Returns
        -------
        func_type : FuncType
        """
        func_type = FuncType.FUNC
        if self._scope_stack[-1].type == FuncType.CLASS:
            func_type = FuncType.METHOD
            for decorator in func_def.decorators:
                if not hasattr(decorator.decorator, "value"):
                    continue
                if decorator.decorator.value == "classmethod":
                    func_type = FuncType.CLASSMETHOD
                    break
                if decorator.decorator.value == "staticmethod":
                    assert func_type == FuncType.METHOD
                    func_type = FuncType.STATICMETHOD
                    break
        return func_type

    def _pytypes_from_node(self, node):
        """Extract types from function, class or module docstrings.

        Parameters
        ----------
        node : cst.FunctionDef | cst.ClassDef | cst.Module

        Returns
        -------
        pytypes : dict[str, ~._docstrings.PyType]
        """
        pytypes = None
        docstring = node.get_docstring()
        if docstring:
            try:
                pytypes = collect_pytypes(docstring, inspector=self.inspector)
            except Exception as e:
                logger.exception(
                    "error while parsing docstring of `%s`:\n\n%s",
                    node.name.value,
                    e,
                )
        return pytypes
