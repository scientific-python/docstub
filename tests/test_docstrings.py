from textwrap import dedent

import pytest

from docstub._analysis import PyImport
from docstub._docstrings import (
    Annotation,
    DocstringAnnotations,
    doctype_to_annotation,
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


class Test_doctype_to_annotation:
    def test_unknown_name(self, caplog):
        # Simple unknown name is aliased to typing.Any
        annotation = doctype_to_annotation("a")
        assert annotation.value == "a"
        assert annotation.imports == {
            PyImport(import_="Incomplete", from_="_typeshed", as_="a")
        }
        assert caplog.messages == ["Unknown name in doctype: 'a'"]

    def test_unknown_qualname(self, caplog):
        # Unknown qualified name is escaped and aliased to typing.Any as well
        annotation = doctype_to_annotation("a.b")
        assert annotation.value == "a_b"
        assert annotation.imports == {
            PyImport(import_="Incomplete", from_="_typeshed", as_="a_b")
        }
        assert caplog.messages == ["Unknown name in doctype: 'a.b'"]

    def test_multiple_unknown_names(self, caplog):
        # Multiple names are aliased to typing.Any
        annotation = doctype_to_annotation("a.b of c")
        assert annotation.value == "a_b[c]"
        assert annotation.imports == {
            PyImport(import_="Incomplete", from_="_typeshed", as_="a_b"),
            PyImport(import_="Incomplete", from_="_typeshed", as_="c"),
        }
        assert sorted(caplog.messages) == [
            "Unknown name in doctype: 'a.b'",
            "Unknown name in doctype: 'c'",
        ]


class Test_DocstringAnnotations:
    def test_empty_docstring(self):
        docstring = dedent("""No sections in this docstring.""")
        annotations = DocstringAnnotations(docstring)
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
        annotations = DocstringAnnotations(docstring)
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
        annotations = DocstringAnnotations(docstring)
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
        annotations = DocstringAnnotations(docstring)
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
        annotations = DocstringAnnotations(docstring)
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
        annotations = DocstringAnnotations(docstring)
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
        annotations = DocstringAnnotations(docstring)
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
        annotations = DocstringAnnotations(docstring)
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
        annotations = DocstringAnnotations(docstring)
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
        annotations = DocstringAnnotations(docstring)
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
        annotations = DocstringAnnotations(docstring)
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
        annotations = DocstringAnnotations(docstring)
        assert len(annotations.parameters) == 3
        assert annotations.parameters["a"].value == "bool"
        assert annotations.parameters["b"].value == "bool"
        assert annotations.parameters["c"].value == "bool"

        assert "d" not in annotations.parameters
        assert "e" not in annotations.parameters

    @pytest.mark.filterwarnings("default:Unknown section:UserWarning:numpydoc")
    def test_unknown_section_logged(self, caplog):
        docstring = dedent(
            """
            Parameters
            ----------
            a : bool

            To Do
            -----
            An unknown section
            """
        )
        annotations = DocstringAnnotations(docstring)
        assert len(annotations.parameters) == 1
        assert annotations.parameters["a"].value == "bool"

        assert caplog.messages == ["Warning in NumPyDoc while parsing docstring"]
        assert caplog.records[0].details == "Unknown section To Do"
