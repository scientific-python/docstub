"""Transform Python source files to typed stub files.

"""

import logging
import fnmatch
from pathlib import Path
from typing import Literal

import libcst as cst

from ._docstrings import collect_pytypes, ReturnKey

logger = logging.getLogger(__name__)


def walk_python_package(root_dir, target_dir):
    """Iterate modules in a Python package and it's target stub files.

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
    for root, dirs, files in root_dir.walk(top_down=True):
        for name in files:
            source_path = root / name

            if name.startswith("test_"):
                logger.debug("skipping %s", name)
                continue

            if source_path.suffix.lower() not in {".py", ".pyi"}:
                continue

            if (
                source_path.suffix.lower() == ".py"
                and source_path.with_suffix(".pyi").exists()
            ):
                # Stub file already exists and takes precedence
                continue

            stub_path = target_dir / source_path.with_suffix(".pyi").relative_to(
                root_dir
            )
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

    def __init__(self, *, docnames):
        self.docnames = docnames
        # Relevant docstring for the current context
        self._context_pytypes = None
        self._required_type_imports = None

    def python_to_stub(self, source: str) -> str:
        """Convert Python source code to stub-file ready code."""
        try:
            self._context_pytypes = []
            self._required_type_imports = set()

            source_tree = cst.parse_module(source)
            stub_tree = source_tree.visit(self)
            stub = stub_tree.code
            stub = try_format_stub(stub)
            return stub
        finally:
            self._context_pytypes = None
            self._required_type_imports = None

    def visit_FunctionDef(self, node):
        docstring = node.get_docstring()
        pytypes = None
        if docstring:
            try:
                pytypes = collect_pytypes(docstring, docnames=self.docnames)
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
            return_pytype = pytypes.get(ReturnKey)
            if return_pytype:
                node_changes["returns"] = cst.Annotation(
                    cst.parse_expression(return_pytype.value)
                )
                self._required_type_imports |= return_pytype.imports

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
            pytype = pytypes.get(name)
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
        """Create nodes to include in the module tree from given imports.

        Parameters
        ----------
        imports : set[DocName]

        Returns
        -------
        import_nodes : tuple[cst.SimpleStatementLine, ...]
        """
        lines = {imp.format_import() for imp in imports}
        import_nodes = tuple(cst.parse_statement(line) for line in lines)
        return import_nodes
