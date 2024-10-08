from textwrap import dedent

import libcst as cst
import libcst.matchers as cstm
import pytest

from docstub._stubs import Py2StubTransformer, _get_docstring_node


class Test_get_docstring_node:
    def test_func(self):
        docstring = dedent(
            '''
        """First line of docstring.

            Parameters
            ----------
            a : int
                Description of `a`.
            b : float, optional

            """
        '''
        ).strip()

        code = dedent(
            '''
        def foo(a, b=None):
            """First line of docstring.

            Parameters
            ----------
            a : int
                Description of `a`.
            b : float, optional

            """
            """Another multiline string

            that  isn't the docstring.
            """
            return a + b
        '''
        )
        module = cst.parse_module(code)

        matches = cstm.findall(module, cstm.FunctionDef())
        assert len(matches) == 1
        func_def = matches[0]

        docstring_node = _get_docstring_node(func_def)

        assert docstring_node.value == docstring

    def test_func_without_docstring(self):
        code = '''
        def foo(a, b=None):
            c = a + b
            """Another multiline string

            that  isn't the docstring.
            """
            return c
        '''
        code = dedent(code)
        module = cst.parse_module(code)

        matches = cstm.findall(module, cstm.FunctionDef())
        assert len(matches) == 1
        func_def = matches[0]

        docstring_node = _get_docstring_node(func_def)

        assert docstring_node is None


class Test_Py2StubTransformer:

    def test_default_None(self):
        # Appending `| None` if a doctype is marked as "optional"
        # is only correct if the default is actually None
        # Ref: https://github.com/scientific-python/docstub/issues/13
        source = dedent(
            '''
        def foo(a=None, b=1):
            """
            Parameters
            ----------
            a : int, optional
            b : int, optional
            """
        '''
        )
        expected = "def foo(a: int | None = ..., b: int = ...) -> None: ..."

        transformer = Py2StubTransformer()
        result = transformer.python_to_stub(source)
        assert expected in result

    # fmt: off
    @pytest.mark.parametrize(
        ("assign", "expected"),
        [
            ("annotated: int",                  "annotated: int"),
            # No implicit optional for values of `None`
            ("annotated_value: int = None",     "annotated_value: int = ..."),
            ("undocumented_assign = None",      "undocumented_assign: Any = ..."),
            # Type aliases are untouched
            ("annot_alias: TypeAlias = int",    "annot_alias: TypeAlias = int"),
            ("type type_stmt = int",            "type type_stmt = int"),
            # Unpacking assignments are expanded
            ("a, b = (4, 5)",                   "a: Any = ...; b: Any = ..."),
            ("x, *y = (4, 5)",                  "x: Any = ...; y: Any = ..."),
            # All is untouched
            ("__all__ = ['foo']",               "__all__ = ['foo']"),
            ("__all__: list[str] = ['foo']",    "__all__: list[str] = ['foo']"),
        ],
    )
    @pytest.mark.parametrize("scope", ["module", "class", "nested class"])
    def test_attributes_no_docstring(self, assign, expected, scope):
        src = assign
        if scope == "class":
            src = f"class TopLevel:\n    {assign}"""
        if scope == "nested class":
            src = f"class TopLevel:\n    class Nested:\n        {assign}"""

        transformer = Py2StubTransformer()
        result = transformer.python_to_stub(src, try_format=False)
        assert expected in result
        if "Any" in result:
            assert "from typing import Any" in result
    # fmt: on
