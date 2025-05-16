from textwrap import dedent

import lark
import pytest

from docstub._analysis import KnownImport
from docstub._docstrings import Annotation, DocstringAnnotations, DoctypeTransformer


class Test_Annotation:
    def test_str(self):
        annotation = Annotation(
            value="Path",
            imports=frozenset({KnownImport(import_name="Path", import_path="pathlib")}),
        )
        assert str(annotation) == annotation.value

    def test_as_return_tuple(self):
        path_anno = Annotation(
            value="Path",
            imports=frozenset({KnownImport(import_name="Path", import_path="pathlib")}),
        )
        sequence_anno = Annotation(
            value="Sequence",
            imports=frozenset(
                {KnownImport(import_name="Sequence", import_path="collections.abc")}
            ),
        )
        return_annotation = Annotation.many_as_tuple([path_anno, sequence_anno])
        assert return_annotation.value == "tuple[Path, Sequence]"
        assert return_annotation.imports == path_anno.imports | sequence_anno.imports

    def test_unexpected_value(self):
        with pytest.raises(ValueError, match="unexpected '~' in annotation value"):
            Annotation(value="~.foo")


class Test_DoctypeTransformer:
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
    def test_natlang_container(self, doctype, expected):
        transformer = DoctypeTransformer()
        annotation, _ = transformer.doctype_to_annotation(doctype)
        assert annotation.value == expected

    @pytest.mark.parametrize(
        "doctype",
        [
            "list of (float)",
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
            ("{'a', 1, None, False}", "Literal['a', 1, None, False]"),
            ("dict[{'a', 'b'}, int]", "dict[Literal['a', 'b'], int]"),
            ("{SomeEnum.FIRST}", "Literal[SomeEnum_FIRST]"),
            ("{`SomeEnum.FIRST`, 1}", "Literal[SomeEnum_FIRST, 1]"),
            ("{:ref:`SomeEnum.FIRST`, 2}", "Literal[SomeEnum_FIRST, 2]"),
            ("{:py:ref:`SomeEnum.FIRST`, 3}", "Literal[SomeEnum_FIRST, 3]"),
        ],
    )
    def test_literals(self, doctype, expected):
        transformer = DoctypeTransformer()
        annotation, _ = transformer.doctype_to_annotation(doctype)
        assert annotation.value == expected

    @pytest.mark.parametrize(
        ("doctype", "expected"),
        [
            ("int, optional", "int"),
            ("int | None, optional", "int | None"),
            ("int, default -1", "int"),
            ("int, default = 1", "int"),
            ("int, default: 0", "int"),
            ("float, default: 1.0", "float"),
            ("{'a', 'b'}, default : 'a'", "Literal['a', 'b']"),
        ],
    )
    @pytest.mark.parametrize("extra_info", [None, "int", ", extra, info"])
    def test_optional_extra_info(self, doctype, expected, extra_info):
        if extra_info:
            doctype = f"{doctype}, {extra_info}"
        transformer = DoctypeTransformer()
        annotation, _ = transformer.doctype_to_annotation(doctype)
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
            ("{shape} {name}",                            "{name}"),
            ("{shape} {name} of {dtype}",                 "{name}[{dtype}]"),
            ("{shape} {dtype} {name}",                    "{name}[{dtype}]"),
            ("{dtype} {name}",                            "{name}[{dtype}]"),
            ("{name} of shape {shape} and dtype {dtype}", "{name}[{dtype}]"),
            ("{name} of dtype {dtype} and shape {shape}", "{name}[{dtype}]"),
        ],
    )
    @pytest.mark.parametrize("name", ["array", "ndarray", "array-like", "array_like"])
    @pytest.mark.parametrize("dtype", ["int", "np.int8"])
    @pytest.mark.parametrize("shape", ["(2, 3)", "(N, m)", "3D", "2-D", "(N, ...)"])
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

    def test_unknown_name(self):
        # Simple unknown name is aliased to typing.Any
        transformer = DoctypeTransformer()
        annotation, unknown_names = transformer.doctype_to_annotation("a")
        assert annotation.value == "a"
        assert annotation.imports == {
            KnownImport(
                import_name="Incomplete", import_path="_typeshed", import_alias="a"
            )
        }
        assert unknown_names == [("a", 0, 1)]

    def test_unknown_qualname(self):
        # Unknown qualified name is escaped and aliased to typing.Any as well
        transformer = DoctypeTransformer()
        annotation, unknown_names = transformer.doctype_to_annotation("a.b")
        assert annotation.value == "a_b"
        assert annotation.imports == {
            KnownImport(
                import_name="Incomplete", import_path="_typeshed", import_alias="a_b"
            )
        }
        assert unknown_names == [("a.b", 0, 3)]

    def test_multiple_unknown_names(self):
        # Multiple names are aliased to typing.Any
        transformer = DoctypeTransformer()
        annotation, unknown_names = transformer.doctype_to_annotation("a.b of c")
        assert annotation.value == "a_b[c]"
        assert annotation.imports == {
            KnownImport(
                import_name="Incomplete", import_path="_typeshed", import_alias="a_b"
            ),
            KnownImport(
                import_name="Incomplete", import_path="_typeshed", import_alias="c"
            ),
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
        assert len(annotations.parameters) == 2
        assert annotations.parameters["a"].value == expected
        assert annotations.parameters["b"].value == "Incomplete"
        assert annotations.parameters["b"].imports == {
            KnownImport.typeshed_Incomplete()
        }

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
        assert annotations.returns.value == "Generator[tuple[int, str]]"
        assert annotations.returns.imports == {
            KnownImport(import_path="collections.abc", import_name="Generator")
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
        assert (
            annotations.returns.value
            == "Generator[tuple[int, str], tuple[float, bytes]]"
        )
        assert annotations.returns.imports == {
            KnownImport(import_path="collections.abc", import_name="Generator")
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
        assert annotations.returns.value == (
            "Generator[tuple[int, str], tuple[float, bytes], bool]"
        )
        assert annotations.returns.imports == {
            KnownImport(import_path="collections.abc", import_name="Generator")
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
        assert annotations.returns.value == ("Generator[tuple[int, str], None, bool]")
        assert annotations.returns.imports == {
            KnownImport(import_path="collections.abc", import_name="Generator")
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

    def test_missing_whitespace(self, capsys):
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
        captured = capsys.readouterr()
        assert "Possibly missing whitespace" in captured.out
