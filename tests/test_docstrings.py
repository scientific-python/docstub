import pytest

from docstub._analysis import KnownImport, StaticInspector, common_known_imports
from docstub._docstrings import DoctypeTransformer


@pytest.fixture()
def transformer():
    inspector = StaticInspector(known_imports=common_known_imports())
    transformer = DoctypeTransformer(inspector=inspector, replace_doctypes={})
    return transformer


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
    def test_container(self, raw, expected, transformer):
        annotation = transformer.transform(raw)
        assert annotation.value == expected
    # fmt: on

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("{'a', 1, None, False}", "Literal['a', 1, None, False]"),
            ("dict[{'a', 'b'}, int]", "dict[Literal['a', 'b'], int]"),
        ],
    )
    def test_literals(self, raw, expected, transformer):
        annotation = transformer.transform(raw)

        assert annotation.value == expected
        assert annotation.imports == frozenset(
            {KnownImport(import_path="typing", import_name="Literal")}
        )

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
    def test_optional_extra_info(self, raw, expected, extra_info, transformer):
        doctype = raw
        if extra_info:
            doctype = f"{doctype}, {extra_info}"

        annotation = transformer.transform(doctype)

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
    def test_shape_n_dtype(self, fmt, expected_fmt, name, dtype, shape, transformer):
        doctype = fmt.format(name=name, dtype=dtype, shape=shape)
        expected = expected_fmt.format(name=name, dtype=dtype, shape=shape)

        annotation = transformer.transform(doctype)

        assert annotation.value == expected
    # fmt: on
