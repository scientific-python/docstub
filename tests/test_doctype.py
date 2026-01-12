import logging

import lark
import lark.exceptions
import pytest

from docstub._doctype import BLACKLISTED_QUALNAMES, parse_doctype


class Test_parse_doctype:
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
            parse_doctype(doctype)

    @pytest.mark.parametrize("doctype", BLACKLISTED_QUALNAMES)
    def test_reserved_keywords(self, doctype):
        with pytest.raises(lark.exceptions.VisitError):
            parse_doctype(doctype)

    @pytest.mark.parametrize(
        ("doctype", "expected"),
        [
            ("int or float", "int | float"),
            ("int or float or str", "int | float | str"),
        ],
    )
    def test_natlang_union(self, doctype, expected):
        expr = parse_doctype(doctype)
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
        expr = parse_doctype(doctype)
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
        expr = parse_doctype(doctype)
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
            parse_doctype(doctype)

    @pytest.mark.parametrize(
        ("doctype", "expected"),
        [
            ("{0}", "Literal[0]"),
            ("{-1, 1}", "Literal[-1, 1]"),
            ("{None}", "Literal[None]"),
            ("{True, False}", "Literal[True, False]"),
            ("""{'a', "bar"}""", """Literal['a', "bar"]"""),
            # Enum
            ("{SomeEnum.FIRST}", "Literal[SomeEnum_FIRST]"),
            ("{`SomeEnum.FIRST`, 1}", "Literal[SomeEnum_FIRST, 1]"),
            ("{:ref:`SomeEnum.FIRST`, 2}", "Literal[SomeEnum_FIRST, 2]"),
            ("{:py:ref:`SomeEnum.FIRST`, 3}", "Literal[SomeEnum_FIRST, 3]"),
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
    def test_literals(self, doctype, expected):
        expr = parse_doctype(doctype)
        assert expr.as_code() == expected

    def test_single_natlang_literal_warning(self, caplog):
        expr = parse_doctype("{True}")
        assert expr.as_code() == "Literal[True]"
        assert caplog.messages == ["Natural language literal with one item: `{True}`"]
        assert caplog.records[0].levelno == logging.WARNING
        assert (
            caplog.records[0].details
            == "Consider using `Literal[True]` to improve readability"
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
        expr = parse_doctype(doctype_with_optional)
        assert expr.as_code() == expected

    @pytest.mark.parametrize(
        ("doctype", "expected"),
        [
            ("`Generator`", "Generator"),
            (":class:`Generator`", "Generator"),
            (":py:class:`Generator`", "Generator"),
            (":py:class:`Generator`[int]", "Generator[int]"),
            (":py:ref:`~.Foo`[int]", "_Foo[int]"),
            ("list[:py:class:`Generator`]", "list[Generator]"),
        ],
    )
    def test_rst_role(self, doctype, expected):
        expr = parse_doctype(doctype)
        assert expr.as_code() == expected

    # fmt: off
    @pytest.mark.parametrize(
        ("fmt", "expected_fmt"),
        [
            ("{name} of shape {shape} and dtype {dtype}", "{name}[{dtype}]"),
            ("{name} of dtype {dtype} and shape {shape}", "{name}[{dtype}]"),
            ("{name} of {dtype}", "{name}[{dtype}]"),
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
        expr = parse_doctype(doctype)
        assert expr.as_code() == expected
    # fmt: on

    @pytest.mark.parametrize(
        ("doctype", "expected"),
        [
            ("ndarray of dtype (int or float)", "ndarray[int | float]"),
        ],
    )
    def test_natlang_array_specific(self, doctype, expected):
        expr = parse_doctype(doctype)
        assert expr.as_code() == expected

    @pytest.mark.parametrize("shape", ["(-1, 3)", "(1.0, 2)", "-3D", "-2-D"])
    def test_natlang_array_invalid_shape(self, shape):
        doctype = f"array of shape {shape}"
        with pytest.raises(lark.exceptions.UnexpectedInput):
            _ = parse_doctype(doctype)

    def test_unknown_name(self):
        # Simple unknown name is aliased to typing.Any
        annotation, unknown_names = parse_doctype("a")
        assert annotation.value == "a"
        assert annotation.imports == {
            PyImport(import_="Incomplete", from_="_typeshed", as_="a")
        }
        assert unknown_names == [("a", 0, 1)]

    def test_unknown_qualname(self):
        # Unknown qualified name is escaped and aliased to typing.Any as well
        annotation, unknown_names = parse_doctype("a.b")
        assert annotation.value == "a_b"
        assert annotation.imports == {
            PyImport(import_="Incomplete", from_="_typeshed", as_="a_b")
        }
        assert unknown_names == [("a.b", 0, 3)]

    def test_multiple_unknown_names(self):
        # Multiple names are aliased to typing.Any
        annotation, unknown_names = parse_doctype("a.b of c")
        assert annotation.value == "a_b[c]"
        assert annotation.imports == {
            PyImport(import_="Incomplete", from_="_typeshed", as_="a_b"),
            PyImport(import_="Incomplete", from_="_typeshed", as_="c"),
        }
        assert unknown_names == [("a.b", 0, 3), ("c", 7, 8)]
