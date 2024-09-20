import pytest

from docstub._docstrings import DoctypeTransformer


class Test_DoctypeTransformer:
    # fmt: off
    @pytest.mark.parametrize(
        ("raw", "expected"),
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
    def test_container(self, raw, expected):
        transformer = DoctypeTransformer()
        annotation, _ = transformer.doctype_to_annotation(raw)
        assert annotation.value == expected
    # fmt: on

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("{'a', 1, None, False}", "Literal['a', 1, None, False]"),
            ("dict[{'a', 'b'}, int]", "dict[Literal['a', 'b'], int]"),
        ],
    )
    def test_literals(self, raw, expected):
        transformer = DoctypeTransformer()
        annotation, _ = transformer.doctype_to_annotation(raw)
        assert annotation.value == expected

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("int, optional", "int | None"),
            # None isn't appended, since the type should cover the default
            ("int, default 1", "int"),
            ("int, default = 1", "int"),
            ("int, default: 1", "int"),
        ],
    )
    @pytest.mark.parametrize("extra_info", [None, "int", ", extra, info"])
    def test_optional_extra_info(self, raw, expected, extra_info):
        doctype = raw
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
