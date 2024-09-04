import pytest

from docstub._analysis import KnownImport, StaticInspector


class Test_StaticInspector:
    known_imports = {  # noqa: RUF012
        "dict": KnownImport(builtin_name="dict"),
        "np": KnownImport(import_name="numpy", import_alias="np"),
        "foo.bar": KnownImport(import_path="foo", import_name="bar"),
        "foo.bar.Baz": KnownImport(import_path="foo.bar", import_name="Baz"),
        "foo.bar.Baz.Bix": KnownImport(import_path="foo.bar", import_name="Baz"),
        "foo.bar.Baz.Qux": KnownImport(import_path="foo", import_name="bar"),
    }

    # fmt: off
    @pytest.mark.parametrize(
        ("name", "exp_annotation", "exp_import_line"),
        [
            ("np", "np", "import numpy as np"),
            # Finds imports whose import target matches the start of `name`
            ("np.doesnt_exist", "np.doesnt_exist", "import numpy as np"),

            ("foo.bar.Baz", "Baz", "from foo.bar import Baz"),
            # Finds "Baz" with abbreviated form as well
            (  "~.bar.Baz", "Baz", "from foo.bar import Baz"),
            (      "~.Baz", "Baz", "from foo.bar import Baz"),

            # Finds nested class "Baz.Bix"
            ("foo.bar.Baz.Bix", "Baz.Bix", "from foo.bar import Baz"),
            (  "~.bar.Baz.Bix", "Baz.Bix", "from foo.bar import Baz"),
            (      "~.Baz.Bix", "Baz.Bix", "from foo.bar import Baz"),
            (          "~.Bix", "Baz.Bix", "from foo.bar import Baz"),

            # Finds nested class "Baz.Gul" that's not explicitly defined, but
            # whose import target matches "Baz"
            ("foo.bar.Baz.Gul", "Baz.Gul", "from foo.bar import Baz"),
            # but abbreviated form doesn't work
            (  "~.bar.Baz.Gul",      None,                      None),
            (      "~.Baz.Gul",      None,                      None),
            (          "~.Gul",      None,                      None),

            # Finds nested class "bar.Baz.Qux" (import defines module as target)
            ("foo.bar.Baz.Qux", "bar.Baz.Qux", "from foo import bar"),
            (  "~.bar.Baz.Qux", "bar.Baz.Qux", "from foo import bar"),
            (      "~.Baz.Qux", "bar.Baz.Qux", "from foo import bar"),
            (          "~.Qux", "bar.Baz.Qux", "from foo import bar"),
        ]
    )
    def test_query(self, name, exp_annotation, exp_import_line):
        inspector = StaticInspector(known_imports=self.known_imports.copy())

        annotation, known_import = inspector.query(name)

        if exp_annotation is None and exp_import_line is None:
            assert exp_annotation is annotation
            assert exp_import_line is known_import
        else:
            assert str(known_import) == exp_import_line
            assert annotation.startswith(known_import.target)
            assert annotation == exp_annotation
    # fmt: on
