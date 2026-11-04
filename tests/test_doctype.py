import logging
from itertools import product

import lark
import lark.exceptions
import pytest

from docstub.doctype import (
    BLACKLISTED_QUALNAMES,
    DoctypeTransformer,
    DoctypeTranspiler,
    Expr,
    Term,
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

    @pytest.mark.parametrize("doctype", BLACKLISTED_QUALNAMES)
    def test_reserved_keywords(self, doctype):
        with pytest.raises(lark.exceptions.VisitError):
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

    @pytest.mark.parametrize(
        ("doctype", "expected"),
        [
            # Conventional
            ("list[float]", "list[float]"),
            ("dict[str, Union[int, str]]", "dict[str, Union[int, str]]"),
            ("tuple[int, ...]", "tuple[int, ...]"),
            ("Sequence[int | float]", "Sequence[int | float]"),
            # Natural language variant with "of" and optional plural "(s)"
            ("list of int", "list[int]"),
            ("list of int(s)", "list[int]"),
            # Natural tuple variant
            ("tuple of (float, int, str)", "tuple[float, int, str]"),
            ("tuple of (float, ...)", "tuple[float, ...]"),
            # Natural dict variant
            ("dict of {str: int}", "dict[str, int]"),
            ("dict of {str: int | float}", "dict[str, int | float]"),
            ("dict of {str: int or float}", "dict[str, int | float]"),
            ("dict[list of str]", "dict[list[str]]"),
        ],
    )
    def test_subscription(self, doctype, expected):
        expr = DoctypeTranspiler()(doctype)
        assert expr.as_code() == expected

    @pytest.mark.parametrize(
        ("doctype", "expected"),
        [
            # Natural language variant with "of" and optional plural "(s)"
            ("list of int", "list[int]"),
            ("list of int(s)", "list[int]"),
            ("list of (int or float)", "list[int | float]"),
            ("list of (list of int)", "list[list[int]]"),
            # Natural tuple variant
            ("tuple of (float, int, str)", "tuple[float, int, str]"),
            ("tuple of (float, ...)", "tuple[float, ...]"),
            # Natural dict variant
            ("dict of {str: int}", "dict[str, int]"),
            ("dict of {str: int | float}", "dict[str, int | float]"),
            ("dict of {str: int or float}", "dict[str, int | float]"),
            # Nesting is possible but probably rarely a good idea
            ("list of (list of int(s))", "list[list[int]]"),
            ("tuple of (tuple of (float, ...), ...)", "tuple[tuple[float, ...], ...]"),
            ("dict of {str: dict of {str: float}}", "dict[str, dict[str, float]]"),
            ("dict of {str: list of (list of int(s))}", "dict[str, list[list[int]]]"),
        ],
    )
    def test_natlang_container(self, doctype, expected):
        expr = DoctypeTranspiler()(doctype)
        assert expr.as_code() == expected

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
        ("doctype"),
        [
            "Literal[0]",
            "Literal[-1, 1]",
            "Literal[None]",
            "Literal[True, False]",
            """Literal['a', "bar"]""",
            # Enum
            "Literal[SomeEnum.FIRST]",
            "Literal[SomeEnum.FIRST, 1]",
            "Literal[SomeEnum.FIRST, 2]",
            "Literal[SomeEnum.FIRST, 3]",
            # Nesting
            "dict[Literal['a', 'b'], int]",
            # Custom qualname for literal
            "MyLiteral[0]",
            "MyLiteral[SomeEnum.FIRST]",
        ],
    )
    def test_literals(self, doctype):
        expr = DoctypeTranspiler()(doctype)
        assert expr.as_code() == doctype
        assert "literal" in [e.rule for e in expr.sub_expressions]

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
            ("{-2., 1.}", "Literal[-2., 1.]"),
            pytest.param(
                "{-inf, inf, nan}",
                "Literal[, 1.]",
                marks=pytest.mark.xfail(reason="unsure how to support"),
            ),
        ],
    )
    def test_natlang_literals(self, doctype, expected):
        expr = DoctypeTranspiler()(doctype)
        assert expr.as_code() == expected
        assert "natlang_literal" in [e.rule for e in expr.sub_expressions]

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
            ("int | None", "int | None"),
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
        assert "callable" in [e.rule for e in expr.sub_expressions]

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
        assert "callable" not in [e.rule for e in expr.sub_expressions]

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

    # fmt: off
    @pytest.mark.parametrize(
        ("fmt", "expected_fmt"),
        [
            ("{name} of shape {shape} and dtype {dtype}", "{name}[{dtype}]"),
            ("{name} of dtype {dtype} and shape {shape}", "{name}[{dtype}]"),
        ],
    )
    @pytest.mark.parametrize("name", ["array", "ndarray", "array-like", "array_like"])
    @pytest.mark.parametrize("dtype", ["int", "np.int8"])
    @pytest.mark.parametrize("shape",
        ["(2, 3)", "(N, m)", "3D", "2-D", "(N, ...)", "([P,] M, N)"]
     )
    def test_natlang_array(self, fmt, expected_fmt, name, dtype, shape):
        doctype = fmt.format(name=name, dtype=dtype, shape=shape)
        expected = expected_fmt.format(name=name, dtype=dtype, shape=shape)
        expr = DoctypeTranspiler()(doctype)
        assert expr.as_code() == expected
        assert "natlang_array" in [e.rule for e in expr.sub_expressions]
    # fmt: on

    @pytest.mark.parametrize(
        ("doctype", "expected"),
        [
            ("ndarray of dtype (int or float)", "ndarray[int | float]"),
            ("ndarray of shape (M, N)", "ndarray"),
        ],
    )
    def test_natlang_array_specific(self, doctype, expected):
        expr = DoctypeTranspiler()(doctype)
        assert expr.as_code() == expected
        assert "natlang_array" in [e.rule for e in expr.sub_expressions]

    @pytest.mark.parametrize("shape", ["(-1, 3)", "(1.0, 2)", "-3D", "-2-D"])
    def test_natlang_array_invalid_shape(self, shape):
        doctype = f"array of shape {shape}"
        with pytest.raises(lark.exceptions.UnexpectedInput):
            _ = DoctypeTranspiler()(doctype)


class Test_DoctypeTranspiler_override:

    @pytest.mark.parametrize(
        ("doctype", "expected"),
        [
            ("ndarray of dtype uint8 or int", "ndarray[uint8] | int"),
            ("ndarray of dtype in {uint8, uint16}", "ndarray[uint8 | uint16]"),
            # ("ndarray of dtype (uint8, uint16)", "ndarray[uint8 | uint16]"),
        ],
    )
    def test_in_dtype(self, doctype, expected):
        grammar = """
        %import doctype (start, dtype, qualname, WS_INLINE)
        dtype_union : "in {" qualname ("," qualname)+ "}" -> union
        %override dtype: qualname | dtype_union
        %ignore WS_INLINE
        """
        transpile = DoctypeTranspiler(grammar=grammar)
        expr = transpile(doctype)
        assert expr.as_code() == expected
        assert "natlang_array" in [e.rule for e in expr.sub_expressions]
        assert "dtype" in [e.rule for e in expr.sub_expressions]

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
        assert "union" in [e.rule for e in expr.sub_expressions]

    @pytest.mark.parametrize(
        ("doctype", "expected"),
        [
            ("(int) -> bool", "Callable[[int], bool]"),
            ("(str, bytes) -> int or bool", "Callable[[str, bytes], int | bool]"),
        ],
    )
    def test_natlang_callable(self, doctype, expected):
        grammar = """
        %import doctype (start, _type, WS_INLINE)
        params: _type ("," _type)*
        natlang_callable : "(" params ") ->" _type
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
                out = DoctypeTransformer._format_subscription(
                    items, rule="natlang_callable"
                )
                return out

        transpile = DoctypeTranspiler(grammar=grammar, transformer=Transformer())
        expr = transpile(doctype)
        assert expr.as_code() == expected
        assert "natlang_callable" in [e.rule for e in expr.sub_expressions]
        assert "params" in [e.rule for e in expr.sub_expressions]

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

        class ExpansionTransformer(DoctypeTransformer):
            def start(self, children):
                children = map(self._expand_expression, children)
                return Expr(rule="start", children=tuple(children))

            def expansion(self, children):
                return Expr(rule="expansion", children=tuple(children))

            def _expand_expression(self, expr):
                expansions = expr.filter(rule="expansion")
                if not expansions:
                    return expr

                # Create Cartesian product of all expansions where each
                # value is prefixed by the expansion it will replace
                expansions = [
                    [(expansion, value) for value in expansion.children]
                    for expansion in expansions
                ]
                combinations = list(product(*expansions))

                # Create a new expression for each combination
                interpolated = []
                for combination in combinations:
                    new_expr = expr
                    for expansion, value in combination:
                        new_expr = new_expr.replace(expansion, value)
                    interpolated.append(new_expr)

                # Join new expressions as union
                full_expr = self.union(lark.Tree("union", children=interpolated))
                return full_expr

        transpile = DoctypeTranspiler(
            grammar=grammar, transformer=ExpansionTransformer()
        )
        expr = transpile(doctype)
        assert expr.as_code() == expected
        assert list(expr.filter(rule="natlang_array")) == []
