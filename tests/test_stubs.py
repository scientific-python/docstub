import logging
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

        assert isinstance(func_def, cst.FunctionDef)
        docstring_node = _get_docstring_node(func_def)

        assert isinstance(docstring_node, cst.SimpleString)
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

        assert isinstance(func_def, cst.FunctionDef)
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
    # TODO Refactor so that there's less overlap between tests
    #   For many cases, the tests aren't very focused on only a single property.
    #   A change / fix might affect more tests than it should. Additionally,
    #   the tests are sensitive to non-meaningful whitespace.

    def test_default_None(self):
        # Appending `| None` if a doctype is marked as "optional"
        # is only correct if the default is actually None
        # Ref: https://github.com/scientific-python/docstub/issues/13

        # TODO use literal values for simple defaults
        #   https://typing.readthedocs.io/en/latest/guides/writing_stubs.html#functions-and-methods

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
        expected = dedent(
            """
            def foo(a: int | None=..., b: int=...) -> None: ...
            """
        )

        transformer = Py2StubTransformer()
        result = transformer.python_to_stub(source)
        assert expected == result

    def test_optional_without_default(self):
        source = dedent(
            '''
            def foo(a):
                """
                Parameters
                ----------
                a : int, optional
                """
            '''
        )
        expected = dedent(
            """
            def foo(a: int) -> None: ...
            """
        )

        transformer = Py2StubTransformer()
        # TODO should warn about a required arg being marked "optional"
        result = transformer.python_to_stub(source)
        assert expected == result

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
        else:
            assert scope == "nested class"
            src = NESTED_CLASS_ATTRIBUTE_TEMPLATE.format(assign=assign, doctype="")

        transformer = Py2StubTransformer()
        result = transformer.python_to_stub(src)

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
            # Keep pre-existing annotations
            ("annotated: float = 1.0", "annotated : int", "annotated: float"),
            # Type aliases are untouched
            ("alias: TypeAlias = int", "alias : str",     "alias: TypeAlias = int"),
            ("type alias = int",       "alias : str",     "type alias = int"),
        ],
    )
    @pytest.mark.parametrize("scope", ["module", "class", "nested class"])
    def test_attributes_with_doctype(self, assign, doctype, expected, scope):
        if scope == "module":
            src = MODULE_ATTRIBUTE_TEMPLATE.format(assign=assign, doctype=doctype)
        elif scope == "class":
            src = CLASS_ATTRIBUTE_TEMPLATE.format(assign=assign, doctype=doctype)
        else:
            assert scope == "nested class"
            src = NESTED_CLASS_ATTRIBUTE_TEMPLATE.format(assign=assign, doctype=doctype)

        transformer = Py2StubTransformer()
        result = transformer.python_to_stub(src)

        # Find exactly one occurrence of `expected`
        pattern = f"^ *({re.escape(expected)})$"
        matches = re.findall(pattern, result, flags=re.MULTILINE)
        assert [matches] == [[expected]], result

        # Docstrings are stripped
        assert "'''" not in result
        assert '"""' not in result
        if "Incomplete" in result:
            assert "from _typeshed import Incomplete" in result
    # fmt: on

    def test_class_init_attributes(self):
        src = dedent(
            """
            class Foo:
                '''
                Attributes
                ----------
                a : int
                b : float
                c : tuple
                d : ClassVar[bool]
                '''

                c: list
                d = True

                def __init__(self, a):
                    self.a = a
                    self.e = None
            """
        )
        expected = dedent(
            """
            from _typeshed import Incomplete
            from typing import ClassVar
            class Foo:
                a: int
                b: float

                c: list
                d: ClassVar[bool]

                def __init__(self, a: Incomplete) -> None: ...
            """
        )
        transformer = Py2StubTransformer()
        result = transformer.python_to_stub(src)
        assert result == expected

    def test_undocumented_objects(self):
        # TODO test undocumented objects
        #  https://typing.readthedocs.io/en/latest/guides/writing_stubs.html#undocumented-objects
        pass

    def test_keep_assign_param(self):
        source = dedent(
            """
            a: str
            """
        )
        expected = dedent(
            """
            a: str
            """
        )
        transformer = Py2StubTransformer()
        result = transformer.python_to_stub(source)
        assert expected == result

    def test_module_assign_conflict(self, caplog):
        source = dedent(
            '''
            """
            Attributes
            ----------
            a : int
            """
            a: str
            '''
        )
        expected = dedent(
            """
            a: str
            """
        )
        transformer = Py2StubTransformer()
        result = transformer.python_to_stub(source)
        assert expected == result

        assert caplog.messages == ["Keeping existing inline annotation for assignment"]
        assert "ignoring docstring: int" in caplog.records[0].details
        assert caplog.records[0].levelno == logging.WARNING

    def test_module_assign_no_conflict(self, capsys):
        source = dedent(
            '''
            """
            Attributes
            ----------
            a :
                No type info here; it's already inlined.
            b : float
            """
            a: int
            b = 3
            '''
        )
        expected = dedent(
            """
            a: int
            b: float
            """
        )
        transformer = Py2StubTransformer()
        result = transformer.python_to_stub(source)
        assert expected == result

        # No warning should have been raised, since there is no conflict
        # between docstring and inline annotation
        output = capsys.readouterr()
        assert output.out == ""

    def test_class_assign_keep_inline_annotation(self):
        source = dedent(
            """
            class Foo:
                a: str
            """
        )
        expected = dedent(
            """
            class Foo:
                a: str
            """
        )
        transformer = Py2StubTransformer()
        result = transformer.python_to_stub(source)
        assert expected == result

    def test_class_assign_conflict(self, caplog):
        source = dedent(
            '''
            class Foo:
                """
                Attributes
                ----------
                a : Sized
                """
                a: str
            '''
        )
        expected = dedent(
            """
            class Foo:
                a: str
            """
        )
        transformer = Py2StubTransformer()
        result = transformer.python_to_stub(source)
        assert expected == result

        assert caplog.messages == ["Keeping existing inline annotation for assignment"]
        assert caplog.records[0].levelno == logging.WARNING

    def test_class_assign_no_conflict(self, caplog):
        source = dedent(
            '''
            class Foo:
                """
                Attributes
                ----------
                a :
                    No type info here; it's already inlined.
                b : float
                """
                a: int
                b = 3
            '''
        )
        expected = dedent(
            """
            class Foo:
                a: int
                b: float
            """
        )
        transformer = Py2StubTransformer()
        result = transformer.python_to_stub(source)
        assert expected == result

        # No warning should have been raised, since there is no conflict
        # between docstring and inline annotation
        assert caplog.messages == []

    def test_param_keep_inline_annotation(self):
        source = dedent(
            """
            def foo(a: str) -> None:
                pass
            """
        )
        expected = dedent(
            """
            def foo(a: str) -> None: ...
            """
        )
        transformer = Py2StubTransformer()
        result = transformer.python_to_stub(source)
        assert expected == result

    def test_param_conflict(self, caplog):
        source = dedent(
            '''
            def foo(a: int) -> None:
                """
                Parameters
                ----------
                a : Sized
                """
                pass
            '''
        )
        expected = dedent(
            """
            def foo(a: int) -> None: ...
            """
        )
        transformer = Py2StubTransformer()
        result = transformer.python_to_stub(source)
        assert expected == result

        assert caplog.messages == ["Keeping existing inline parameter annotation"]
        assert "ignoring docstring: Sized" in caplog.records[0].details
        assert caplog.records[0].levelno == logging.WARNING

    @pytest.mark.parametrize("missing", ["", "b", "b :"])
    def test_missing_param(self, missing, caplog):
        source = dedent(
            f'''
            def foo(a, b) -> None:
                """
                Parameters
                ----------
                a : int
                {missing}
                """
            '''
        )
        expected = dedent(
            """
            from _typeshed import Incomplete
            def foo(a: int, b: Incomplete) -> None: ...
            """
        )
        transformer = Py2StubTransformer()
        result = transformer.python_to_stub(source)
        assert expected == result
        assert caplog.messages == ["Missing annotation for parameter 'b'"]
        assert caplog.records[0].levelno == logging.WARNING

    def test_missing_param_inline(self, caplog):
        source = dedent(
            """
            def foo(a: int, b) -> None:
                pass
            """
        )
        expected = dedent(
            """
            from _typeshed import Incomplete
            def foo(a: int, b: Incomplete) -> None: ...
            """
        )
        transformer = Py2StubTransformer()
        result = transformer.python_to_stub(source)
        assert expected == result
        assert caplog.messages == ["Missing annotation for parameter 'b'"]
        assert caplog.records[0].levelno == logging.WARNING

    @pytest.mark.parametrize("missing", ["", "b", "b :"])
    def test_missing_attr(self, missing, caplog):
        source = dedent(
            f'''
            class Foo:
                """
                Attributes
                ----------
                a : ClassVar[int]
                {missing}
                """
                a = 3
                b = True
            '''
        )
        expected = dedent(
            """
            from _typeshed import Incomplete
            from typing import ClassVar
            class Foo:
                a: ClassVar[int]
                b: Incomplete
            """
        )
        transformer = Py2StubTransformer()
        result = transformer.python_to_stub(source)
        assert expected == result
        assert caplog.messages == ["Missing annotation for assignment 'b'"]
        assert caplog.records[0].levelno == logging.WARNING

    def test_missing_attr_inline(self, caplog):
        source = dedent(
            """
            from typing import ClassVar
            class Foo:
                a: ClassVar[int] = 3
                b = True
            """
        )
        expected = dedent(
            """
            from _typeshed import Incomplete
            from typing import ClassVar
            class Foo:
                a: ClassVar[int]
                b: Incomplete
            """
        )
        transformer = Py2StubTransformer()
        result = transformer.python_to_stub(source)
        assert expected == result
        assert caplog.messages == ["Missing annotation for assignment 'b'"]
        assert caplog.records[0].levelno == logging.WARNING

    def test_return_keep_inline_annotation(self):
        source = dedent(
            """
            def foo() -> str:
                pass
            """
        )
        expected = dedent(
            """
            def foo() -> str: ...
            """
        )
        transformer = Py2StubTransformer()
        result = transformer.python_to_stub(source)
        assert expected == result

    def test_return_conflict(self, caplog):
        source = dedent(
            '''
            def foo() -> int:
                """
                Returns
                -------
                out : Sized
                """
                pass
            '''
        )
        expected = dedent(
            """
            def foo() -> int: ...
            """
        )
        transformer = Py2StubTransformer()
        result = transformer.python_to_stub(source)
        assert expected == result

        assert caplog.messages == ["Keeping existing inline return annotation"]
        assert "ignoring docstring: Sized" in caplog.records[0].details
        assert caplog.records[0].levelno == logging.WARNING

    def test_preserved_type_comment(self):
        source = dedent(
            """
            # Import untyped library
            import untyped  # type: ignore
            """
        )
        expected = dedent(
            """

            import untyped  # type: ignore
            """
        )
        transformer = Py2StubTransformer()
        result = transformer.python_to_stub(source)
        assert expected == result

    @pytest.mark.xfail(reason="not supported yet")
    def test_preserved_comments_extended(self):
        source = dedent(
            """
            # Import untyped library
            import untyped  # type: ignore

            class Foo:
                a = 3  # type: int

            def bar(x: str) -> None:  # undocumented
              pass
            """
        )
        expected = dedent(
            """
            import untyped  # type: ignore

            class Foo:
                a = 3  # type: int

            def bar(x: str) -> None: ...  # undocumented
            """
        )

        transformer = Py2StubTransformer()
        result = transformer.python_to_stub(source)
        assert expected == result

    def test_on_off_comment(self):
        source = dedent(
            """
            class Foo:
                '''
                Parameters
                ----------
                a
                b
                c
                d
                '''
                # docstub: off
                a: int = None
                b: str = ""
                # docstub: on
                c: int = None
                d: str = ""
            """
        )
        expected = dedent(
            """
            class Foo:

                a: int = None
                b: str = ""

                c: int
                d: str
            """
        )
        transformer = Py2StubTransformer()
        result = transformer.python_to_stub(source)
        # Removing the comments leaves the whitespace from the indent,
        # remove these empty lines from the result too
        result = dedent(result)
        assert expected == result

    @pytest.mark.parametrize("decorator", ["dataclass", "dataclasses.dataclass"])
    def test_dataclass(self, decorator):
        source = dedent(
            f"""
            @{decorator}
            class Foo:
                a: float
                b: int = 3
                c: str = None
                _: KW_ONLY
                d: dict[str, Any] = field(default_factory=dict)
                e: InitVar[tuple] = tuple()
                f: ClassVar
                g: ClassVar[float]
                h: Final[ClassVar[int]] = 1
            """
        )
        expected = dedent(
            f"""
            @{decorator}
            class Foo:
                a: float
                b: int = ...
                c: str = ...
                _: KW_ONLY
                d: dict[str, Any] = ...
                e: InitVar[tuple] = ...
                f: ClassVar
                g: ClassVar[float]
                h: Final[ClassVar[int]]
            """
        )
        transformer = Py2StubTransformer()
        result = transformer.python_to_stub(source)
        assert expected == result

    def test_args_kwargs(self):
        # Unpack and TypedDict (PEP 692) are not yet considered / supported
        source = dedent(
            """
            def foo(*args, **kwargs):
                '''
                Parameters
                ----------
                *args : str
                **kwargs : int
                '''
            """
        )
        expected = dedent(
            """
            def foo(*args: str, **kwargs: int) -> None: ...
            """
        )
        transformer = Py2StubTransformer()
        result = transformer.python_to_stub(source)
        assert expected == result
