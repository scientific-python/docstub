"""Transform Python source files to typed stub files."""

import enum
import logging
from dataclasses import dataclass

import libcst as cst
import libcst.matchers as cstm

from ._analysis import KnownImport
from ._docstrings import DocstringAnnotations, DoctypeTransformer
from ._utils import ContextFormatter, module_name_from_path

logger = logging.getLogger(__name__)


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

    Yields
    ------
    source_path : Path
        Either a Python file or a stub file that takes precedence.
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

        yield path


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
    source_path : Path
        Either a Python file or a stub file that takes precedence.
    stub_path : Path
        Target stub file.

    Notes
    -----
    Files starting with "test_" are skipped entirely for now.
    """
    for source_path in walk_source(root_dir):
        stub_path = target_dir / source_path.with_suffix(".pyi").relative_to(root_dir)
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


class FuncType(enum.StrEnum):
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


def _get_docstring_node(node):
    """Extract the node with the docstring from a definition.

    Unfortunately, libcst's builtin `get_docstring` returns the value of the
    docstring itself and not the wrapping node. In order to extract the
    position of the docstring we need the node itself.

    Parameters
    ----------
    node : cst.FunctionDef | cst.ClassDef | cst.Module

    Returns
    -------
    docstring_node :  cst.SimpleString | cst.ConcatenatedString | None
        The node of the docstring if found.
    """
    docstring_node = None

    docstring = node.get_docstring(clean=False)
    if docstring:
        # Workaround to find the exact postion of a docstring
        # by using its node
        string_nodes = cstm.findall(
            node, cstm.SimpleString() | cstm.ConcatenatedString()
        )
        matching_nodes = [
            node for node in string_nodes if node.evaluated_value == docstring
        ]
        assert len(matching_nodes) == 1
        docstring_node = matching_nodes[0]

    return docstring_node


class Py2StubTransformer(cst.CSTTransformer):
    """Transform syntax tree of a Python file into the tree of a stub file [1]_.

    Attributes
    ----------
    types_db : ~.TypesDatabase

    References
    ----------
    .. [1] Stub file specification https://typing.readthedocs.io/en/latest/spec/distributing.html#stub-files
    """

    METADATA_DEPENDENCIES = (cst.metadata.PositionProvider,)

    _docstub_generated_comment = cst.EmptyLine(
        comment=cst.Comment(
            "# Generated with docstub. Manual edits will be overwritten!"
        ),
    )

    # Equivalent to ` ...`, to replace the body of callables with
    _body_replacement = cst.SimpleStatementSuite(
        leading_whitespace=cst.SimpleWhitespace(value=" "),
        body=[cst.Expr(value=cst.Ellipsis())],
    )
    _Annotation_Any = cst.Annotation(cst.Name("Any"))
    _Annotation_None = cst.Annotation(cst.Name("None"))

    def __init__(self, *, types_db=None, replace_doctypes=None):
        """
        Parameters
        ----------
        types_db : ~.TypesDatabase
        replace_doctypes : dict[str, str]
        """
        self.types_db = types_db
        self.replace_doctypes = replace_doctypes
        self.transformer = DoctypeTransformer(
            types_db=types_db, replace_doctypes=replace_doctypes
        )
        # Relevant docstring for the current context
        self._scope_stack = None  # Entered module, class or function scopes
        self._pytypes_stack = None  # Collected pytypes for each stack
        self._required_imports = None  # Collect imports for used types
        self._current_module = None

        self._current_source = None  # Use via property `current_source`

    @property
    def current_source(self):
        return self._current_source

    @current_source.setter
    def current_source(self, value):
        self._current_source = value
        if self.types_db is not None:
            self.types_db.current_source = value

    def python_to_stub(self, source, *, module_path=None, try_format=True):
        """Convert Python source code to stub-file ready code.

        Parameters
        ----------
        source  : str
        module_path : Path, optional
            The location of the source that is transformed into a stub file.
            If given, used to enhance logging & error messages with more
            context information.
        try_format : bool, optional
            Try to format the output, if the appropriate dependencies are
            installed.

        Returns
        -------
        stub : str
        """
        try:
            self._scope_stack = []
            self._pytypes_stack = []
            self._required_imports = set()
            self.current_source = module_path

            source_tree = cst.parse_module(source)
            source_tree = cst.metadata.MetadataWrapper(source_tree)
            stub_tree = source_tree.visit(self)
            stub = stub_tree.code
            if try_format is True:
                stub = try_format_stub(stub)
            return stub
        finally:
            self._scope_stack = None
            self._pytypes_stack = None
            self._required_imports = None
            self.current_source = None

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
        pytypes = self._annotations_from_node(node)
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
        pytypes = self._annotations_from_node(node)
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

        ds_annotations = self._pytypes_stack.pop()
        if ds_annotations and ds_annotations.returns:
            assert ds_annotations.returns.value
            node_changes["returns"] = cst.Annotation(
                cst.parse_expression(ds_annotations.returns.value)
            )
            self._required_imports |= ds_annotations.returns.imports

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
        defaults_to_none = cstm.matches(updated_node.default, cstm.Name(value="None"))

        if updated_node.default is not None:
            node_changes["default"] = cst.Ellipsis()

        name = original_node.name.value
        pytypes = self._pytypes_stack[-1]
        if not pytypes and scope.is_class_init:
            pytypes = self._pytypes_stack[-2]

        if pytypes:
            pytype = pytypes.parameters.get(name)
            if pytype:
                if defaults_to_none:
                    pytype = pytype.as_optional()
                annotation = cst.Annotation(cst.parse_expression(pytype.value))
                node_changes["annotation"] = annotation
                if pytype.imports:
                    self._required_imports |= pytype.imports

        # Potentially use "Any" except for first param in (class)methods
        elif not is_self_or_cls and updated_node.annotation is None:
            node_changes["annotation"] = self._Annotation_Any
            import_ = KnownImport(import_path="typing", import_name="Any")
            self._required_imports.add(import_)

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
        """Handle assignment statements without annotations.

        Parameters
        ----------
        original_node : cst.Assign
        updated_node : cst.Assign

        Returns
        -------
        updated_node : cst.Assign or cst.FlattenSentinel
        """
        target_names = [
            name.value
            for target in updated_node.targets
            for name in cstm.findall(target, cstm.Name())
        ]
        if "__all__" in target_names:
            logger.warning(
                "found `__all__` in assignment with multiple targets, not modifying it"
            )
            return updated_node

        assert len(original_node.targets) > 0
        if len(target_names) == 1:
            # Replace with annotated assignment
            updated_node = self._replace_assign_with_annotated(
                updated_node.targets[0].target
            )

        else:
            # Unpack assignment with multiple targets into multple annotated ones
            # e.g. `x, y = (1, 2)` -> `x: Any = ...; y: Any = ...`
            unpacked = []
            for name in target_names:
                is_last = name == target_names[-1]
                sub_node = self._replace_assign_with_annotated(
                    cst.Name(name), trailing_semicolon=not is_last
                )
                unpacked.append(sub_node)
            updated_node = cst.FlattenSentinel(unpacked)

        return updated_node

    def leave_AnnAssign(self, original_node, updated_node):
        """Handle annotated assignment statements.

        Replace values of annotated assignments with ``...``, except when
        the assignment target is `__all__` or the annotation is `TypeAlias`.

        Parameters
        ----------
        original_node : cst.AnnAssign
        updated_node : cst.AnnAssign

        Returns
        -------
        updated_node : cst.AnnAssign
        """
        is_type_alias = cstm.matches(
            updated_node.annotation, cstm.Annotation(cstm.Name("TypeAlias"))
        )
        is__all__ = cstm.matches(updated_node.target, cstm.Name("__all__"))
        if updated_node.value is not None and not is_type_alias and not is__all__:
            updated_node = updated_node.with_changes(value=cst.Ellipsis())
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
        pytypes = self._annotations_from_node(node)
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
        required_imports = self._required_imports.copy()
        current_module = None
        if self.current_source:
            current_module = module_name_from_path(self.current_source)
            required_imports = [
                imp
                for imp in self._required_imports
                if imp.import_path != current_module
            ]
        import_nodes = self._parse_imports(
            required_imports, current_module=current_module
        )
        updated_node = updated_node.with_changes(
            header=[self._docstub_generated_comment],
            body=import_nodes + updated_node.body,
        )
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
        imports : set[~.KnownImport]
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

    def _annotations_from_node(self, node):
        """Extract types from function, class or module docstrings.

        Parameters
        ----------
        node : cst.FunctionDef | cst.ClassDef | cst.Module

        Returns
        -------
        annotations : ~.DocstringAnnotations
        """
        annotations = None

        docstring_node = _get_docstring_node(node)
        if docstring_node:
            position = self.get_metadata(
                cst.metadata.PositionProvider, docstring_node
            ).start

            ctx = ContextFormatter(path=self.current_source, line=position.line)
            try:
                annotations = DocstringAnnotations(
                    docstring_node.evaluated_value,
                    transformer=self.transformer,
                    ctx=ctx,
                )
            except (SystemExit, KeyboardInterrupt):
                raise
            except Exception as e:
                logger.exception(
                    "error while parsing docstring of `%s`:\n\n%s",
                    node.name.value,
                    e,
                )
        return annotations

    def _replace_assign_with_annotated(self, target, *, trailing_semicolon=False):
        """Create an annotated assign."""
        semicolon = (
            cst.Semicolon(whitespace_after=cst.SimpleWhitespace(" "))
            if trailing_semicolon
            else cst.MaybeSentinel.DEFAULT
        )
        node = cst.AnnAssign(
            target=target,
            annotation=self._Annotation_Any,
            value=cst.Ellipsis(),
            semicolon=semicolon,
        )
        self._required_imports.add(KnownImport.Any())
        return node
