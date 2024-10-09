import re
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


MODULE_ATTRIBUTE_TEMPLATE = '''\
"""Module docstring.

Attributes
----------
{doctype}
"""

{assign}
'''

CLASS_ATTRIBUTE_TEMPLATE = '''\
class TopLevel:
    """Class docstring.

    Attributes
    ----------
    {doctype}
    """

    {assign}
'''

NESTED_CLASS_ATTRIBUTE_TEMPLATE = '''\
class TopLevel:
    class Nested:
        """Class docstring.

        Attributes
        ----------
        {doctype}
        """

        {assign}
'''


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
            ("annotated_value: int = None",     "annotated_value: int"),
            ("undocumented_assign = None",      "undocumented_assign: Incomplete"),
            # Type aliases are untouched
            ("annot_alias: TypeAlias = int",    "annot_alias: TypeAlias = int"),
            ("type type_stmt = int",            "type type_stmt = int"),
            # Unpacking assignments are expanded
            ("a, b = (4, 5)",                   "a: Incomplete; b: Incomplete"),
            ("x, *y = (4, 5)",                  "x: Incomplete; y: Incomplete"),
            # All is untouched
            ("__all__ = ['foo']",               "__all__ = ['foo']"),
            ("__all__: list[str] = ['foo']",    "__all__: list[str] = ['foo']"),
        ],
    )
    @pytest.mark.parametrize("scope", ["module", "class", "nested class"])
    def test_attributes_no_doctype(self, assign, expected, scope):
        if scope == "module":
            src = MODULE_ATTRIBUTE_TEMPLATE.format(assign=assign, doctype="")
        elif scope == "class":
            src = CLASS_ATTRIBUTE_TEMPLATE.format(assign=assign, doctype="")
        elif scope == "nested class":
            src = NESTED_CLASS_ATTRIBUTE_TEMPLATE.format(assign=assign, doctype="")

        transformer = Py2StubTransformer()
        result = transformer.python_to_stub(src, try_format=False)

        # Find exactly one occurrence of `expected`
        pattern = f"^ *({re.escape(expected)})$"
        matches = re.findall(pattern, result, flags=re.MULTILINE)
        assert [matches] == [[expected]], result

        # Docstrings are stripped
        assert "'''" not in result
        assert '"""' not in result
        if "Any" in result:
            assert "from typing import Any" in result
    # fmt: on

    # fmt: off
    @pytest.mark.parametrize(
        ("assign", "doctype", "expected"),
        [
            ("plain = 3",       "plain : int",  "plain: int"),
            ("plain = None",    "plain : int",  "plain: int"),
            ("x, y = (1, 2)",   "x : int",      "x: int; y: Incomplete"),
            # Replace pre-existing annotations
            ("annotated: float = 1.0", "annotated : int", "annotated: int"),
            # Type aliases are untouched
            ("alias: TypeAlias = int", "alias: str",      "alias: TypeAlias = int"),
            ("type alias = int",       "alias: str",      "type alias = int"),
        ],
    )
    # @pytest.mark.parametrize("scope", ["module", "class", "nested class"])
    @pytest.mark.parametrize("scope", ["module"])
    def test_attributes_with_doctype(self, assign, doctype, expected, scope):
        if scope == "module":
            src = MODULE_ATTRIBUTE_TEMPLATE.format(assign=assign, doctype=doctype)
        elif scope == "class":
            src = CLASS_ATTRIBUTE_TEMPLATE.format(assign=assign, doctype=doctype)
        elif scope == "nested class":
            src = NESTED_CLASS_ATTRIBUTE_TEMPLATE.format(assign=assign, doctype=doctype)

        transformer = Py2StubTransformer()
        result = transformer.python_to_stub(src, try_format=False)

        # Find exactly one occurrence of `expected`
        pattern = f"^ *({re.escape(expected)})$"
        matches = re.findall(pattern, result, flags=re.MULTILINE)
        assert [matches] == [[expected]], result

        # Docstrings are stripped
        assert "'''" not in result
        assert '"""' not in result
        if "Any" in result:
            assert "from typing import Any" in result
    # fmt: on
