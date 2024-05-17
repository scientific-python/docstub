"""Transform Python source files to typed stub files.

"""

from dataclasses import dataclass

from pathlib import Path

# Potential alternative(?): parso
import libcst as cst

from ._docstrings import transform_docstring


class ImportSpec(dict):
    def __init__(self, spec):
        super().__init__(
            ((rule, obj.split("::")) for rule, obj in spec.items())
        )


class TreeTransformer(cst.CSTTransformer):
    """Transform syntax tree of a Python file into the tree of a stub file."""

    # Equivalent to ` ...`, to replace the body of callables with
    _body_replacement = cst.SimpleStatementSuite(
        leading_whitespace=cst.SimpleWhitespace(value=' '),
        body=[cst.Expr(value=cst.Ellipsis())],
    )

    def __init__(self, transform_docstring):
        self.transform_docstring = transform_docstring
        # Relevant docstring for the current context
        self._context_doctypes = []
        self._used_type_names = []

    def python_to_stub(self, source):
        source_tree = cst.parse_module(source)
        stub_tree = source_tree.visit(self)
        return stub_tree.code

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
        updated_node = updated_node.with_changes(
            body=self._body_replacement
        )
        self._context_doctypes.pop()
        return updated_node

    def leave_Param(self, original_node, updated_node):
        name = original_node.name.value
        assert original_node.annotation is None
        doctypes = self._context_doctypes[-1]
        if doctypes:
            annotation = cst.Annotation(
                cst.parse_expression(doctypes.params[name])
            )
            updated_node = updated_node.with_changes(annotation=annotation)
        return updated_node

    def leave_Module(self, original_node, updated_node):
        # TODO prepend imports!
        return updated_node


