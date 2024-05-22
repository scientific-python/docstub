"""Transform Python source files to typed stub files.

"""

import black


# Potential alternative(?): parso
import libcst as cst


class TreeTransformer(cst.CSTTransformer):
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
        if docstring:
            doctypes = self.transform_docstring(docstring)
            self._context_doctypes.append(doctypes)
        else:
            self._context_doctypes.append(None)
        return True

    def leave_FunctionDef(self, original_node, updated_node):
        updated_node = updated_node.with_changes(body=self._body_replacement)
        self._context_doctypes.pop()
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
        return updated_node

    def leave_Expr(self, original_node, upated_node):
        return cst.RemovalSentinel.REMOVE

    def leave_Module(self, original_node, updated_node):
        type_imports = {str(imp) for imp in self._required_type_imports}
        type_imports = sorted(type_imports)
        type_imports = tuple(cst.parse_statement(line) for line in type_imports)
        updated_node = updated_node.with_changes(body=type_imports + updated_node.body)
        return updated_node
