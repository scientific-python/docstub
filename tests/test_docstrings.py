from textwrap import dedent

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
                {KnownImport(import_name="Sequence", import_path="typing")}
            ),
        )
        return_annotation = Annotation.as_return_tuple([path_anno, sequence_anno])
        assert return_annotation.value == "tuple[Path, Sequence]"
        assert return_annotation.imports == path_anno.imports | sequence_anno.imports

    def test_unexpected_value(self):
        with pytest.raises(ValueError, match="unexpected '~' in annotation value"):
            Annotation(value="~.foo")


class Test_DoctypeTransformer:
    # fmt: off
    @pytest.mark.parametrize(
        ("doctype", "expected"),
        [
            ("list[float]", "list[float]"),
            ("dict[str, Union[int, str]]", "dict[str, Union[int, str]]"),
            ("tuple[int, ...]", "tuple[int, ...]"),

            ("list of int", "list[int]"),
            ("tuple of float", "tuple[float]"),
            ("tuple of (float, ...)", "tuple[float, ...]"),

            ("Sequence[int | float]", "Sequence[int | float]"),

            ("dict of {str: int}", "dict[str, int]"),
        ],
    )
    def test_container(self, doctype, expected):
        transformer = DoctypeTransformer()
        annotation, _ = transformer.doctype_to_annotation(doctype)
        assert annotation.value == expected
    # fmt: on

    @pytest.mark.parametrize(
        ("doctype", "expected"),
        [
            ("{'a', 1, None, False}", "Literal['a', 1, None, False]"),
            ("dict[{'a', 'b'}, int]", "dict[Literal['a', 'b'], int]"),
            ("{SomeEnum.FIRST}", "Literal[SomeEnum_FIRST]"),
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
            ("list[:py:class:`Generator`]", "list[Generator]"),
        ],
    )
    def test_sphinx_ref(self, doctype, expected):
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
    def test_shape_n_dtype(self, fmt, expected_fmt, name, dtype, shape):

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
        assert not annotations.parameters  # parsing yields no annotation
        captured = capsys.readouterr()
        assert "Possibly missing whitespace" in captured.out
