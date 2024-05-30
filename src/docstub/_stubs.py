"""Transform Python source files to typed stub files.

"""

import logging

import black

import libcst as cst


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
            py_path = root / name
            stub_path = target_dir / py_path.with_suffix(".pyi").relative_to(root_dir)
            yield py_path, stub_path


class Py2StubTransformer(cst.CSTTransformer):
    """Transform syntax tree of a Python file into the tree of a stub file."""

    # Equivalent to ` ...`, to replace the body of callables with
    _body_replacement = cst.SimpleStatementSuite(
        leading_whitespace=cst.SimpleWhitespace(value=" "),
        body=[cst.Expr(value=cst.Ellipsis())],
    )

    def __init__(self, transform_docstring):
        self.transform_docstring = transform_docstring
        # Relevant docstring for the current context
        self._context_doctypes = None
        self._required_type_imports = None

    def python_to_stub(self, source, format=True):
        try:
            self._context_doctypes = []
            self._required_type_imports = []

            source_tree = cst.parse_module(source)
            stub_tree = source_tree.visit(self)
            stub = stub_tree.code
            stub = black.format_str(stub, mode=black.Mode())
            return stub
        finally:
            self._context_doctypes = None
            self._required_type_imports = None

    def visit_Import(self, node):
        return None

    def visit_FunctionDef(self, node):
        docstring = node.get_docstring()
        doctypes = None
        if docstring:
            try:
                doctypes = self.transform_docstring(docstring)
            except Exception as e:
                logger.error(
                    "error while parsing docstring of `%s`:\n\n%s",
                    node.name.value, e
                )
        self._context_doctypes.append(doctypes)
        return True

    def leave_FunctionDef(self, original_node, updated_node):
        updated_node = updated_node.with_changes(body=self._body_replacement)
        return_type = "None"

        context = self._context_doctypes.pop()
        if context:
            return_params = context.return_params
            if return_params:
                if len(return_params) > 1:
                    return_type = f"tuple[{', '.join(r[0] for r in return_params.values())}]"
                else:
                    return_type = return_params[0][0]
        annotation = cst.Annotation(cst.parse_expression(return_type))
        updated_node = updated_node.with_changes(returns=annotation)
        return updated_node

    def leave_Param(self, original_node, updated_node):
        name = original_node.name.value
        assert original_node.annotation is None
        doctypes = self._context_doctypes[-1]
        if doctypes:
            param_type, imports = doctypes.params.get(name, (None, None))
            if param_type:
                annotation = cst.Annotation(cst.parse_expression(param_type))
                updated_node = updated_node.with_changes(annotation=annotation)
            if imports:
                self._required_type_imports.extend(imports)
        if original_node.default is not None:
            updated_node = updated_node.with_changes(default=cst.Ellipsis())
        return updated_node

    def leave_Expr(self, original_node, upated_node):
        return cst.RemovalSentinel.REMOVE

    def leave_Module(self, original_node, updated_node):
        type_imports = {imp.format_import() for imp in self._required_type_imports}
        type_imports = sorted(type_imports)
        type_imports = tuple(cst.parse_statement(line) for line in type_imports)
        updated_node = updated_node.with_changes(body=type_imports + updated_node.body)
        return updated_node
