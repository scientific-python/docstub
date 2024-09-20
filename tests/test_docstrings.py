import pytest

from docstub._analysis import KnownImport
from docstub._docstrings import DoctypeTransformer


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
        ],
    )
    def test_literals(self, doctype, expected):
        transformer = DoctypeTransformer()
        annotation, _ = transformer.doctype_to_annotation(doctype)
        assert annotation.value == expected

    @pytest.mark.parametrize(
        ("doctype", "expected"),
        [
            ("int, optional", "int | None"),
            # None isn't appended, since the type should cover the default
            ("int, default 1", "int"),
            ("int, default = 1", "int"),
            ("int, default: 1", "int"),
        ],
    )
    @pytest.mark.parametrize("extra_info", [None, "int", ", extra, info"])
    def test_optional_extra_info(self, doctype, expected, extra_info):
        if extra_info:
            doctype = f"{doctype}, {extra_info}"
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

        def escape(name):
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
            KnownImport(import_name="Any", import_path="typing", import_alias="a")
        }
        assert unknown_names == [("a", 0, 1)]

    def test_unknown_qualname(self):
        # Unknown qualified name is escaped and aliased to typing.Any as well
        transformer = DoctypeTransformer()
        annotation, unknown_names = transformer.doctype_to_annotation("a.b")
        assert annotation.value == "a_b"
        assert annotation.imports == {
            KnownImport(import_name="Any", import_path="typing", import_alias="a_b")
        }
        assert unknown_names == [("a.b", 0, 3)]

    def test_multiple_unknown_names(self):
        # Multiple names are aliased to typing.Any
        transformer = DoctypeTransformer()
        annotation, unknown_names = transformer.doctype_to_annotation("a.b of c")
        assert annotation.value == "a_b[c]"
        assert annotation.imports == {
            KnownImport(import_name="Any", import_path="typing", import_alias="a_b"),
            KnownImport(import_name="Any", import_path="typing", import_alias="c"),
        }
        assert unknown_names == [("a.b", 0, 3), ("c", 7, 8)]
