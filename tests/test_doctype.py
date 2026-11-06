import logging

import lark
import lark.exceptions
import pytest

from docstub.doctype import (
    FORBIDDEN_KEYWORDS,
    DoctypeTransformer,
    DoctypeTranspiler,
    Expr,
    QualnameIsForbidden,
    Term,
    expand_expression,
    insert_between,
)


class Test_DoctypeTranspiler:
    @pytest.mark.parametrize(
        "doctype",
        [
            "((float))",
            "(float,)",
            "(, )",
            "...",
            "(..., ...)",
            "{}",
            "{:}",
            "{a:}",
            "{:b}",
            "{'a',}",
            "a or (b or c)",
            ",, optional",
        ],
    )
    def test_edge_case_errors(self, doctype):
        with pytest.raises(lark.exceptions.UnexpectedInput):
            DoctypeTranspiler()(doctype)

    @pytest.mark.parametrize("keyword", FORBIDDEN_KEYWORDS)
    @pytest.mark.parametrize("template", ["{}", "Literal[{}]"])
    def test_reserved_keywords(self, keyword, template):
        doctype = template.format(keyword)
        with pytest.raises(QualnameIsForbidden, match=keyword):
            DoctypeTranspiler()(doctype)

    @pytest.mark.parametrize(
        ("doctype", "expected"),
        [
            ("int or float", "int | float"),
            ("int or float or str", "int | float | str"),
        ],
    )
    def test_natlang_union(self, doctype, expected):
        expr = DoctypeTranspiler()(doctype)
        assert expr.as_code() == expected
        assert expr.find_one(rule="union")

    @pytest.mark.parametrize(
        ("doctype", "expected"),
        [
            ("list[float]", "list[float]"),
            ("dict[str, Union[int, str]]", "dict[str, Union[int, str]]"),
            ("tuple[int, ...]", "tuple[int, ...]"),
            ("Sequence[int | float]", "Sequence[int | float]"),
        ],
    )
    def test_subscription(self, doctype, expected):
        expr = DoctypeTranspiler()(doctype)
        assert expr.as_code() == expected
        assert expr.find_all(rule="subscription")

    @pytest.mark.parametrize(
        ("doctype", "expected"),
        [
            # Natural language variant with "of" and optional plural "(s)"
            ("list of int", "list[int]"),
            ("list of int(s)", "list[int]"),
            ("list of (int or float)", "list[int | float]"),
            # Natural tuple variant
            ("tuple of (float, int, str)", "tuple[float, int, str]"),
            ("tuple of (float, ...)", "tuple[float, ...]"),
            # Natural dict variant
            ("dict of {str: int}", "dict[str, int]"),
            ("dict of {str: int | float}", "dict[str, int | float]"),
            ("dict of {str: int or float}", "dict[str, int | float]"),
        ],
    )
    def test_natlang_container(self, doctype, expected):
        expr = DoctypeTranspiler()(doctype)
        assert expr.as_code() == expected
        assert expr.find_one(rule="natlang_container"), expr.format_tree()

    @pytest.mark.parametrize(
        ("doctype", "expected"),
        [
            ("list of (list of int)", "list[list[int]]"),
            ("list of (list of int(s))", "list[list[int]]"),
            ("tuple of (tuple of (float, ...), ...)", "tuple[tuple[float, ...], ...]"),
            ("dict of {str: dict of {str: float}}", "dict[str, dict[str, float]]"),
            ("dict of {str: list of (list of int(s))}", "dict[str, list[list[int]]]"),
        ],
    )
    def test_nested_natlang_container(self, doctype, expected):
        expr = DoctypeTranspiler()(doctype)
        assert expr.as_code() == expected
        assert len(expr.find_all(rule="natlang_container")) > 1

    @pytest.mark.parametrize(
        "doctype",
        [
            "list of int (s)",
            "list of ((float))",
            "list of (float,)",
            "list of (, )",
            "list of ...",
            "list of (..., ...)",
            "dict of {}",
            "dict of {:}",
            "dict of {a:}",
            "dict of {:b}",
        ],
    )
    def test_subscription_error(self, doctype):
        with pytest.raises(lark.exceptions.UnexpectedInput):
            DoctypeTranspiler()(doctype)

    @pytest.mark.parametrize(
        "doctype",
        [
            "Literal[0]",
            "Literal[-1, 1]",
            "Literal[-2., 1.5]",
            """Literal['a', "bar"]""",
            # Enum
            "Literal[SomeEnum.FIRST, 1]",
            "Literal[SomeEnum.FIRST, 2]",
            "Literal[SomeEnum.FIRST, 3]",
            # Nesting
            "dict[Literal['a', 'b'], int]",
        ],
    )
    def test_literals(self, doctype):
        expr = DoctypeTranspiler()(doctype)
        assert expr.as_code() == doctype
        assert expr.find_one(rule="literal")

    @pytest.mark.parametrize(
        "doctype",
        [
            "Literal[None]",
            "Literal[True, False]",
            # Enum
            "Literal[SomeEnum.FIRST]",
        ],
    )
    def test_literal_only_qualnames(self, doctype):
        """Parsed as a subscription because it only contains qualnames."""
        expr = DoctypeTranspiler()(doctype)
        assert expr.as_code() == doctype
        assert expr.find_one(rule="subscription")
        assert not expr.find_all(rule="literal")

    @pytest.mark.parametrize(
        ("doctype", "expected"),
        [
            ("{0}", "Literal[0]"),
            ("{-1, 1}", "Literal[-1, 1]"),
            ("{None}", "Literal[None]"),
            ("{True, False}", "Literal[True, False]"),
            ("""{'a', "bar"}""", """Literal['a', "bar"]"""),
            # Enum
            ("{SomeEnum.FIRST}", "Literal[SomeEnum.FIRST]"),
            ("{`SomeEnum.FIRST`, 1}", "Literal[SomeEnum.FIRST, 1]"),
            ("{:ref:`SomeEnum.FIRST`, 2}", "Literal[SomeEnum.FIRST, 2]"),
            ("{:py:ref:`SomeEnum.FIRST`, 3}", "Literal[SomeEnum.FIRST, 3]"),
            # Nesting
            ("dict[{'a', 'b'}, int]", "dict[Literal['a', 'b'], int]"),
            # These aren't officially valid as an argument to `Literal` (yet)
            # https://typing.python.org/en/latest/spec/literal.html
            # TODO figure out how docstub should deal with these
            ("{-2., 1.5}", "Literal[-2., 1.5]"),
            pytest.param(
                "{-inf, inf, nan}",
                "Literal[-inf, inf, nan]",
                marks=pytest.mark.xfail(reason="unsure if to support"),
            ),
        ],
    )
    def test_natlang_literals(self, doctype, expected):
        expr = DoctypeTranspiler()(doctype)
        assert expr.as_code() == expected
        assert expr.find_one(rule="natlang_literal")

    def test_single_natlang_literal_warning(self, caplog):
        expr = DoctypeTranspiler()("{True}")
        assert expr.as_code() == "Literal[True]"
        assert caplog.messages == ["Natural language literal with one item: `{True}`"]
        assert caplog.records[0].levelno == logging.WARNING
        assert caplog.records[0].details == (
            "Consider using `%s` to improve readability",
            "Literal[True]",
        )

    @pytest.mark.parametrize(
        ("doctype", "expected"),
        [
            ("int", "int"),
            ("tuple of (int, float)", "tuple[int, float]"),
            ("{'a', 'b'}", "Literal['a', 'b']"),
        ],
    )
    @pytest.mark.parametrize(
        "optional_info",
        [
            "",
            ", optional",
            ", default -1",
            ", default: -1",
            ", default = 1",
            ", in range (0, 1), optional",
            ", optional, in range [0, 1]",
            ", see parameter `image`, optional",
        ],
    )
    def test_optional_info(self, doctype, expected, optional_info):
        doctype_with_optional = doctype + optional_info
        expr = DoctypeTranspiler()(doctype_with_optional)
        assert expr.as_code() == expected
        assert not expr.find_all(rule="optional_info")

    @pytest.mark.parametrize(
        "doctype",
        [
            "Callable[[int], str]",
            "some_func[[int], str]",
            "Callable[[int, float, byte], list[str]]",
            "Callable[..., str]",
            "Callable[[], str]",
            "Callback[...]",
        ],
    )
    def test_callable(self, doctype):
        expr = DoctypeTranspiler()(doctype)
        assert expr.as_code() == doctype
        assert expr.find_one(rule="callable")

    @pytest.mark.parametrize(
        "doctype",
        [
            "Callable[Concatenate[int, float], str]",
            "Callable[Concatenate[int, ...], str]",
            "Callable[P, str]",
        ],
    )
    def test_callable_subscriptions_form(self, doctype):
        expr = DoctypeTranspiler()(doctype)
        assert expr.as_code() == doctype
        assert not expr.find_all(rule="callable")

    @pytest.mark.parametrize(
        "doctype",
        [
            "Callable[[...], int]",
            "Callable[[..., str], int]",
            "Callable[[float, str], int, byte]",
        ],
    )
    def test_callable_error(self, doctype):
        with pytest.raises(lark.exceptions.UnexpectedInput):
            DoctypeTranspiler()(doctype)

    @pytest.mark.parametrize(
        ("doctype", "expected"),
        [
            ("`Generator`", "Generator"),
            (":class:`Generator`", "Generator"),
            (":py:class:`Generator`", "Generator"),
            (":py:class:`Generator`[int]", "Generator[int]"),
            (":py:ref:`~.Foo`[int]", "~.Foo[int]"),
            ("list[:py:class:`Generator`]", "list[Generator]"),
        ],
    )
    def test_rst_role(self, doctype, expected):
        expr = DoctypeTranspiler()(doctype)
        assert expr.as_code() == expected
        assert expr.find_one(rule="rst_role")


class Test_DoctypeTranspiler_arrays:
    @pytest.mark.parametrize(
        ("in_shape", "out_shape"),
        [
            # Exact dimensionality
            ("()", "tuple[()]"),  # Special case: 0-D
            ("(M,)", "tuple[int]"),
            ("(M=3,)", "tuple[int]"),
            ("(2,)", "tuple[int]"),
            ("(M, N)", "tuple[int, int]"),
            ("(M, N, O)", "tuple[int, int, int]"),
            ("(0, 1, 2)", "tuple[int, int, int]"),
            # Ellipsis expands to unconstraint shape
            ("(M, ...)", "tuple[Any, ...]"),
            ("(0, ...)", "tuple[Any, ...]"),
            ("(..., M)", "tuple[Any, ...]"),
            ("(M, ..., N)", "tuple[Any, ...]"),
            ("(M[, ...], N)", "tuple[Any, ...]"),
        ],
    )
    def test_explicit_shape(self, in_shape, out_shape):
        """Cases where the shape describes the exact dimensionality"""
        doctype = f"ndarray of shape {in_shape}"
        expected = f"ndarray[{out_shape}]"
        expr = DoctypeTranspiler()(doctype)
        assert expr.as_code() == expected

    @pytest.mark.parametrize(
        ("doctype", "expected"),
        [
            (
                "ndarray of shape (M[, N])",
                "ndarray[tuple[int]] | ndarray[tuple[int, int]]",
            ),
            (
                "ndarray of shape ([M, ]N)",
                "ndarray[tuple[int]] | ndarray[tuple[int, int]]",
            ),
            (
                "ndarray of shape ([N,] M [,O])",
                "ndarray[tuple[int]]"
                " | ndarray[tuple[int, int]]"
                " | ndarray[tuple[int, int, int]]",
            ),
            (
                "ndarray of shape (M[, N, O], P)",
                "ndarray[tuple[int, int]]"
                " | ndarray[tuple[int, int, int]]"
                " | ndarray[tuple[int, int, int, int]]",
            ),
        ],
    )
    def test_optional_shape(self, doctype, expected):
        """Optional dimensions are expanded into union of matching arrays."""
        expr = DoctypeTranspiler()(doctype)
        assert expr.as_code() == expected

    @pytest.mark.parametrize("shape", ["(N)", "(2)", "(-1, 3)", "(1.0, 2)"])
    def test_malformed_shape(self, shape):
        doctype = f"ndarray of shape {shape}"
        with pytest.raises(lark.LexError, match="No terminal matches"):
            DoctypeTranspiler()(doctype)

    @pytest.mark.parametrize(
        ("doctype", "expected"),
        [
            ("ndarray of dtype int", "ndarray[tuple[Any, ...], np.dtype[int]]"),
            (
                "ndarray of dtype (int or float)",
                "ndarray[tuple[Any, ...], np.dtype[int]]"
                " | ndarray[tuple[Any, ...], np.dtype[float]]",
            ),
            (
                "ndarray of dtype (int | float | complex)",
                "ndarray[tuple[Any, ...], np.dtype[int]]"
                " | ndarray[tuple[Any, ...], np.dtype[float]]"
                " | ndarray[tuple[Any, ...], np.dtype[complex]]",
            ),
        ],
    )
    def test_dtype(self, doctype, expected):
        expr = DoctypeTranspiler()(doctype)
        assert expr.as_code() == expected

    @pytest.mark.parametrize(
        ("doctype", "expected"),
        [
            (
                "ndarray of dtype int and shape (M, N)",
                "ndarray[tuple[int, int], np.dtype[int]]",
            ),
            (
                "ndarray of dtype (int or float) and shape ([N,] M)",
                "ndarray[tuple[int], np.dtype[int]]"
                " | ndarray[tuple[int], np.dtype[float]]"
                " | ndarray[tuple[int, int], np.dtype[int]]"
                " | ndarray[tuple[int, int], np.dtype[float]]",
            ),
        ],
    )
    def test_shape_and_dtype(self, doctype, expected):
        expr = DoctypeTranspiler()(doctype)
        assert expr.as_code() == expected

    @pytest.mark.parametrize(
        "fmt",
        [
            "{name} of shape {shape} and dtype {dtype}",
            "{name} of dtype {dtype} and shape {shape}",
        ],
    )
    @pytest.mark.parametrize("name", ["array-like", "array_like"])
    @pytest.mark.parametrize("dtype", ["int", "np.int8"])
    @pytest.mark.parametrize("shape", ["(2, 3)", "(N, m)", "(N, ...)", "([P,] M, N)"])
    def test_natlang_array_like(self, fmt, name, dtype, shape):
        doctype = fmt.format(name=name, dtype=dtype, shape=shape)
        expr = DoctypeTranspiler()(doctype)
        assert expr.as_code() == name
        assert expr.find_one(rule="natlang_array")


class Test_DoctypeTranspiler_override:
    @pytest.mark.parametrize(
        ("doctype", "expected"),
        [
            ("my_array of dtype int", "my_array[tuple[Any, ...], np.dtype[int]]"),
            ("my_array of shape (4,)", "my_array[tuple[int]]"),
        ],
    )
    def test_doc_example_new_array_name(self, doctype, expected):
        grammar = """
        %import doctype (start, WS_INLINE, ARRAY_NAME)
        %extend ARRAY_NAME: "my_array"
        %ignore WS_INLINE
        """
        transpile = DoctypeTranspiler(grammar=grammar)
        expr = transpile(doctype)
        assert expr.as_code() == expected
        assert expr.find_one(rule="natlang_array")

    @pytest.mark.parametrize(
        ("doctype", "expected"),
        [
            ("int or float or complex", "complex | float | int"),
            ("int or tuple[int or float, ...]", "int | tuple[float | int, ...]"),
        ],
    )
    def test_transformer_only(self, doctype, expected):
        @lark.visitors.v_args(tree=True)
        class Transformer(DoctypeTransformer):
            def union(self, tree):
                # Sort items in union alphabetically
                tree.children = sorted(tree.children, key=str)
                out = super().union(tree)
                return out

        transpile = DoctypeTranspiler(transformer=Transformer())
        expr = transpile(doctype)
        assert expr.as_code() == expected
        assert expr.find_all(rule="union")

    @pytest.mark.parametrize(
        ("doctype", "expected"),
        [
            ("f(int) -> bool", "Callable[[int], bool]"),
            ("f(str, bytes) -> int or bool", "Callable[[str, bytes], int | bool]"),
        ],
    )
    def test_natlang_callable(self, doctype, expected):
        grammar = """
        %import doctype (start, _type, WS_INLINE)
        params: _type ("," _type)*
        natlang_callable : "f(" params ") ->" _type
        %extend _type: natlang_callable
        %ignore WS_INLINE
        """

        class Transformer(lark.visitors.Transformer):
            def start(self, children):
                return Expr(rule="start", children=tuple(children))

            def params(self, children):
                sep = Term(", ", kind="syntax")
                content = insert_between(children, sep=sep)
                items = [
                    Term("[", kind="syntax"),
                    *content,
                    Term("]", kind="syntax"),
                ]
                out = Expr(rule="params", children=tuple(items))
                return out

            def natlang_callable(self, children):
                items = [Term("Callable", kind="name"), *children]
                out = DoctypeTransformer._create_subscription_expr(
                    items, rule="natlang_callable"
                )
                return out

        transpile = DoctypeTranspiler(grammar=grammar, transformer=Transformer())
        expr = transpile(doctype)
        assert expr.as_code() == expected
        assert expr.find_one(rule="natlang_callable")
        assert expr.find_all(rule="params")

    @pytest.mark.parametrize(
        ("doctype", "expected"),
        [
            ("{Iterable, Sequence} of int(s)", "Iterable[int] | Sequence[int]"),
            (
                "{list, set} of {int, float}",
                "list[int] | list[float] | set[int] | set[float]",
            ),
        ],
    )
    def test_expansion_of_qualnames(self, doctype, expected):
        grammar = """
        %import doctype (start, WS_INLINE, qualname)
        %extend qualname: "{" qualname ("," qualname)+ "}" -> expansion
        %ignore WS_INLINE
        """

        @lark.visitors.v_args(tree=True)
        class ExpansionTransformer(DoctypeTransformer):
            def start(self, tree):
                """Transform "start" rule.

                Parameters
                ----------
                tree : lark.Tree

                Returns
                -------
                expr : Expr
                """
                assert len(tree.children) == 1
                assert isinstance(tree.children[0], Expr)
                child = expand_expression(tree.children[0], expand_rule="expansion")
                return Expr(rule="start", children=(child,))

        transpile = DoctypeTranspiler(
            grammar=grammar, transformer=ExpansionTransformer()
        )
        expr = transpile(doctype)
        assert expr.as_code() == expected
        assert not expr.find_all(rule="expansion")
