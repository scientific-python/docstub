import logging
from textwrap import dedent

import lark
import pytest

from docstub._analysis import PyImport
from docstub._docstrings import (
    Annotation,
    DocstringAnnotations,
    DoctypeTransformer,
)


class Test_Annotation:
    def test_str(self):
        annotation = Annotation(
            value="Path",
            imports=frozenset({PyImport(import_="Path", from_="pathlib")}),
        )
        assert str(annotation) == annotation.value

    def test_as_return_tuple(self):
        path_anno = Annotation(
            value="Path",
            imports=frozenset({PyImport(import_="Path", from_="pathlib")}),
        )
        sequence_anno = Annotation(
            value="Sequence",
            imports=frozenset({PyImport(import_="Sequence", from_="collections.abc")}),
        )
        return_annotation = Annotation.many_as_tuple([path_anno, sequence_anno])
        assert return_annotation.value == "tuple[Path, Sequence]"
        assert return_annotation.imports == path_anno.imports | sequence_anno.imports

    def test_unexpected_value(self):
        with pytest.raises(ValueError, match=r"unexpected '~' in annotation value"):
            Annotation(value="~.foo")


class Test_DoctypeTransformer:
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
        transformer = DoctypeTransformer()
        with pytest.raises(lark.exceptions.UnexpectedInput):
            transformer.doctype_to_annotation(doctype)

    @pytest.mark.parametrize("doctype", DoctypeTransformer.blacklisted_qualnames)
    def test_reserved_keywords(self, doctype):
        assert DoctypeTransformer.blacklisted_qualnames

        transformer = DoctypeTransformer()
        with pytest.raises(lark.exceptions.VisitError):
            transformer.doctype_to_annotation(doctype)

    @pytest.mark.parametrize(
        ("doctype", "expected"),
        [
            ("int or float", "int | float"),
            ("int or float or str", "int | float | str"),
        ],
    )
    def test_natlang_union(self, doctype, expected):
        transformer = DoctypeTransformer()
        annotation, _ = transformer.doctype_to_annotation(doctype)
        assert annotation.value == expected

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
        transformer = DoctypeTransformer()
        annotation, _ = transformer.doctype_to_annotation(doctype)
        assert annotation.value == expected

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
        transformer = DoctypeTransformer()
        annotation, _ = transformer.doctype_to_annotation(doctype)
        assert annotation.value == expected

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
        transformer = DoctypeTransformer()
        with pytest.raises(lark.exceptions.UnexpectedInput):
            transformer.doctype_to_annotation(doctype)

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
        transformer = DoctypeTransformer()
        annotation, _ = transformer.doctype_to_annotation(doctype)
        assert annotation.value == expected

    def test_single_natlang_literal_warning(self, caplog):
        transformer = DoctypeTransformer()
        annotation, _ = transformer.doctype_to_annotation("{True}")
        assert annotation.value == "Literal[True]"
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
        transformer = DoctypeTransformer()
        annotation, _ = transformer.doctype_to_annotation(doctype_with_optional)
        assert annotation.value == expected

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
        transformer = DoctypeTransformer()
        annotation, _ = transformer.doctype_to_annotation(doctype)
        assert annotation.value == expected

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

        def escape(name: str) -> str:
            return name.replace("-", "_").replace(".", "_")

        doctype = fmt.format(name=name, dtype=dtype, shape=shape)
        expected = expected_fmt.format(
            name=escape(name), dtype=escape(dtype), shape=shape
        )

        transformer = DoctypeTransformer()
        annotation, _ = transformer.doctype_to_annotation(doctype)

        assert annotation.value == expected
    # fmt: on

    @pytest.mark.parametrize(
        ("doctype", "expected"),
        [
            ("ndarray of dtype (int or float)", "ndarray[int | float]"),
        ],
    )
    def test_natlang_array_specific(self, doctype, expected):
        transformer = DoctypeTransformer()
        annotation, _ = transformer.doctype_to_annotation(doctype)
        assert annotation.value == expected

    @pytest.mark.parametrize("shape", ["(-1, 3)", "(1.0, 2)", "-3D", "-2-D"])
    def test_natlang_array_invalid_shape(self, shape):
        doctype = f"array of shape {shape}"
        transformer = DoctypeTransformer()
        with pytest.raises(lark.exceptions.UnexpectedInput):
            _ = transformer.doctype_to_annotation(doctype)

    def test_unknown_name(self):
        # Simple unknown name is aliased to typing.Any
        transformer = DoctypeTransformer()
        annotation, unknown_names = transformer.doctype_to_annotation("a")
        assert annotation.value == "a"
        assert annotation.imports == {
            PyImport(import_="Incomplete", from_="_typeshed", as_="a")
        }
        assert unknown_names == [("a", 0, 1)]

    def test_unknown_qualname(self):
        # Unknown qualified name is escaped and aliased to typing.Any as well
        transformer = DoctypeTransformer()
        annotation, unknown_names = transformer.doctype_to_annotation("a.b")
        assert annotation.value == "a_b"
        assert annotation.imports == {
            PyImport(import_="Incomplete", from_="_typeshed", as_="a_b")
        }
        assert unknown_names == [("a.b", 0, 3)]

    def test_multiple_unknown_names(self):
        # Multiple names are aliased to typing.Any
        transformer = DoctypeTransformer()
        annotation, unknown_names = transformer.doctype_to_annotation("a.b of c")
        assert annotation.value == "a_b[c]"
        assert annotation.imports == {
            PyImport(import_="Incomplete", from_="_typeshed", as_="a_b"),
            PyImport(import_="Incomplete", from_="_typeshed", as_="c"),
        }
        assert unknown_names == [("a.b", 0, 3), ("c", 7, 8)]


class Test_DocstringAnnotations:
    def test_empty_docstring(self):
        docstring = dedent("""No sections in this docstring.""")
        transformer = DoctypeTransformer()
        annotations = DocstringAnnotations(docstring, transformer=transformer)
        assert annotations.attributes == {}
        assert annotations.parameters == {}
        assert annotations.returns is None

    @pytest.mark.parametrize(
        ("doctype", "expected"),
        [
            ("bool", "bool"),
            ("str, extra information", "str"),
            ("list of int, optional", "list[int]"),
        ],
    )
    def test_parameters(self, doctype, expected):
        docstring = dedent(
            f"""
            Parameters
            ----------
            a : {doctype}
            b :
            """
        )
        transformer = DoctypeTransformer()
        annotations = DocstringAnnotations(docstring, transformer=transformer)
        assert len(annotations.parameters) == 1
        assert annotations.parameters["a"].value == expected
        assert "b" not in annotations.parameters

    @pytest.mark.parametrize(
        ("doctypes", "expected"),
        [
            (["bool", "int | None"], "tuple[bool, int | None]"),
            (["tuple of int", "tuple[int, ...]"], "tuple[tuple[int], tuple[int, ...]]"),
        ],
    )
    def test_returns(self, doctypes, expected):
        docstring = dedent(
            """
            Returns
            -------
            a : {}
            b : {}
            """
        ).format(*doctypes)
        transformer = DoctypeTransformer()
        annotations = DocstringAnnotations(docstring, transformer=transformer)
        assert annotations.returns is not None
        assert annotations.returns.value == expected

    def test_yields(self, caplog):
        docstring = dedent(
            """
            Yields
            ------
            a : int
            b : str
            """
        )
        transformer = DoctypeTransformer()
        annotations = DocstringAnnotations(docstring, transformer=transformer)
        assert annotations.returns is not None
        assert annotations.returns.value == "Generator[tuple[int, str]]"
        assert annotations.returns.imports == {
            PyImport(from_="collections.abc", import_="Generator")
        }

    def test_receives(self, caplog):
        docstring = dedent(
            """
            Yields
            ------
            a : int
            b : str

            Receives
            --------
            c : float
            d : bytes
            """
        )
        transformer = DoctypeTransformer()
        annotations = DocstringAnnotations(docstring, transformer=transformer)
        assert annotations.returns is not None
        assert (
            annotations.returns.value
            == "Generator[tuple[int, str], tuple[float, bytes]]"
        )
        assert annotations.returns.imports == {
            PyImport(from_="collections.abc", import_="Generator")
        }

    def test_full_generator(self, caplog):
        docstring = dedent(
            """
            Yields
            ------
            a : int
            b : str

            Receives
            --------
            c : float
            d : bytes

            Returns
            -------
            e : bool
            """
        )
        transformer = DoctypeTransformer()
        annotations = DocstringAnnotations(docstring, transformer=transformer)
        assert annotations.returns is not None
        assert annotations.returns.value == (
            "Generator[tuple[int, str], tuple[float, bytes], bool]"
        )
        assert annotations.returns.imports == {
            PyImport(from_="collections.abc", import_="Generator")
        }

    def test_yields_and_returns(self, caplog):
        docstring = dedent(
            """
            Yields
            ------
            a : int
            b : str

            Returns
            -------
            e : bool
            """
        )
        transformer = DoctypeTransformer()
        annotations = DocstringAnnotations(docstring, transformer=transformer)
        assert annotations.returns is not None
        assert annotations.returns.value == ("Generator[tuple[int, str], None, bool]")
        assert annotations.returns.imports == {
            PyImport(from_="collections.abc", import_="Generator")
        }

    def test_duplicate_parameters(self, caplog):
        docstring = dedent(
            """
            Parameters
            ----------
            a : int
            a : str
            """
        )
        transformer = DoctypeTransformer()
        annotations = DocstringAnnotations(docstring, transformer=transformer)
        assert len(annotations.parameters) == 1
        assert annotations.parameters["a"].value == "int"

    def test_duplicate_returns(self, caplog):
        docstring = dedent(
            """
        Returns
        -------
        a : int
        a : str
        """
        )
        transformer = DoctypeTransformer()
        annotations = DocstringAnnotations(docstring, transformer=transformer)
        assert annotations.returns is not None
        assert annotations.returns is not None
        assert annotations.returns.value == "int"

    def test_args_kwargs(self):
        docstring = dedent(
            """
            Parameters
            ----------
            *args : int
            **kwargs : str
            """
        )
        transformer = DoctypeTransformer()
        annotations = DocstringAnnotations(docstring, transformer=transformer)
        assert "args" in annotations.parameters
        assert "*args" not in annotations.parameters
        assert "kwargs" in annotations.parameters
        assert "**kargs" not in annotations.parameters

    def test_missing_whitespace(self, caplog):
        """Check for warning if a whitespace is missing between parameter and colon.

        In this case, NumPyDoc parses the entire thing as the parameter name.
        """
        docstring = dedent(
            """
            Parameters
            ----------
            a: int
            """
        )
        transformer = DoctypeTransformer()
        annotations = DocstringAnnotations(docstring, transformer=transformer)
        assert annotations.parameters["a"].value == "int"
        assert len(caplog.records) == 1
        assert "Possibly missing whitespace" in caplog.text

    def test_combined_numpydoc_params(self):
        docstring = dedent(
            """
            Parameters
            ----------
            a, b, c : bool
            d, e :
            """
        )
        transformer = DoctypeTransformer()
        annotations = DocstringAnnotations(docstring, transformer=transformer)
        assert len(annotations.parameters) == 3
        assert annotations.parameters["a"].value == "bool"
        assert annotations.parameters["b"].value == "bool"
        assert annotations.parameters["c"].value == "bool"

        assert "d" not in annotations.parameters
        assert "e" not in annotations.parameters
