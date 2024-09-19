from textwrap import dedent

import libcst as cst
import libcst.matchers as cstm

from docstub._stubs import _get_docstring_node


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
