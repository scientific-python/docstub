"""Transform Python source files to typed stub files.

"""

import logging

import libcst as cst

from ._docstrings import CollectedPyTypes

logger = logging.getLogger(__name__)


def walk_python_package(root_dir, target_dir):
    """

    Parameters
    ----------
    root_dir : Path
    target_dir : Path

    Returns
    -------
    py_path : Path
    stub_path : Path
    """
    for root, dirs, files in root_dir.walk(top_down=True):
        for name in files:
            if not name.endswith(".py"):
                continue
            if name.startswith("test_"):
                logger.debug("skipping %s", name)
                continue
            py_path = root / name
            stub_path = target_dir / py_path.with_suffix(".pyi").relative_to(root_dir)
            yield py_path, stub_path


def try_format_stub(stub):
    try:
        import isort

        stub = isort.code(stub)
    except ImportError:
        logger.warning("isort is not available, couldn't sort imports")
    try:
        import black

        stub = black.format_str(stub, mode=black.Mode())
    except ImportError:
        logger.warning("black is not available, couldn't format stubs")
    return stub


class Py2StubTransformer(cst.CSTTransformer):
    """Transform syntax tree of a Python file into the tree of a stub file."""

    # Equivalent to ` ...`, to replace the body of callables with
    _body_replacement = cst.SimpleStatementSuite(
        leading_whitespace=cst.SimpleWhitespace(value=" "),
        body=[cst.Expr(value=cst.Ellipsis())],
    )
    _Annotation_Any = cst.Annotation(cst.Name("Any"))
    _Annotation_None = cst.Annotation(cst.Name("None"))

    def __init__(self, *, docnames, format_stubs=True):
        self.docnames = docnames
        self.format_stubs = format_stubs
        # Relevant docstring for the current context
        self._context_pytypes = None
        self._required_type_imports = None

    def python_to_stub(self, source):
        try:
            self._context_pytypes = []
            self._required_type_imports = set()

            source_tree = cst.parse_module(source)
            stub_tree = source_tree.visit(self)
            stub = stub_tree.code
            if self.format_stubs:
                stub = try_format_stub(stub)
            return stub
        finally:
            self._context_pytypes = None
            self._required_type_imports = None

    def visit_Import(self, node):
        return None

    def visit_FunctionDef(self, node):
        docstring = node.get_docstring()
        pytypes = None
        if docstring:
            try:
                pytypes = CollectedPyTypes.from_docstring(
                    docstring, docnames=self.docnames
                )
            except Exception as e:
                logger.exception(
                    "error while parsing docstring of `%s`:\n\n%s", node.name.value, e
                )
        self._context_pytypes.append(pytypes)
        return True

    def leave_FunctionDef(self, original_node, updated_node):
        node_changes = {
            "body": self._body_replacement,
            "returns": self._Annotation_None,
        }

        pytypes = self._context_pytypes.pop()
        if pytypes:
            if pytypes.returns:
                if len(pytypes.returns) > 1:
                    return_type = (
                        f"tuple[{', '.join(r.value for r in pytypes.returns.values())}]"
                    )
                else:
                    return_type = pytypes.returns[0].value
                node_changes["returns"] = cst.Annotation(
                    cst.parse_expression(return_type)
                )
                for pytype in pytypes.returns.values():
                    self._required_type_imports |= pytype.imports

        updated_node = updated_node.with_changes(**node_changes)
        return updated_node

    def leave_Param(self, original_node, updated_node):
        node_changes = {}

        if updated_node.annotation is None:
            node_changes["annotation"] = self._Annotation_Any
            self._required_type_imports.add(self.docnames["Any"])

        name = original_node.name.value
        pytypes = self._context_pytypes[-1]
        if pytypes:
            pytype = pytypes.params.get(name)
            if pytype:
                annotation = cst.Annotation(cst.parse_expression(pytype.value))
                node_changes["annotation"] = annotation
                if pytype.imports:
                    self._required_type_imports |= pytype.imports

        if updated_node.default is not None:
            node_changes["default"] = cst.Ellipsis()

        if node_changes:
            updated_node = updated_node.with_changes(**node_changes)
        return updated_node

    def leave_Expr(self, original_node, upated_node):
        return cst.RemovalSentinel.REMOVE

    def leave_Comment(self, original_node, updated_node):
        return cst.RemovalSentinel.REMOVE

    def leave_Module(self, original_node, updated_node):
        import_nodes = self._parse_imports(self._required_type_imports)
        updated_node = updated_node.with_changes(body=import_nodes + updated_node.body)
        return updated_node

    @staticmethod
    def _parse_imports(imports):
        lines = {imp.format_import() for imp in imports}
        lines = sorted(lines)  # TODO use isort instead?
        import_nodes = tuple(cst.parse_statement(line) for line in lines)
        return import_nodes
