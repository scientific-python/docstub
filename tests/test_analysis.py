from textwrap import dedent

import pytest

from docstub._analysis import KnownImport, TypeCollector, TypesDatabase


@pytest.fixture
def module_factory(tmp_path):
    """Fixture to help with creating adhoc modules with a given source.

    Parameters
    ----------
    tmp_path : Path

    Returns
    -------
    module_factory : callable
        A callable with the signature `(src: str, module_name: str) -> Path`.
    """

    def _module_factory(src, module_name):
        *parents, name = module_name.split(".")

        cwd = tmp_path
        for parent in parents:
            package = cwd / parent
            package.mkdir()
            (package / "__init__.py").touch()
            cwd = package

        module_path = cwd / f"{name}.py"
        with open(module_path, "w") as fp:
            fp.write(src)

        return module_path

    return _module_factory


class Test_TypeCollector:

    def test_classes(self, module_factory):
        module_path = module_factory(
            src=dedent(
                """
                class TopLevelClass:
                    class NestedClass:
                        pass
                """
            ),
            module_name="sub.module",
        )
        imports = TypeCollector.collect(file=module_path)
        assert len(imports) == 2
        assert imports["sub.module.TopLevelClass"] == KnownImport(
            import_path="sub.module", import_name="TopLevelClass"
        )
        # The import for the nested class should still use only the top-level
        # class as an import target
        assert imports["sub.module.TopLevelClass.NestedClass"] == KnownImport(
            import_path="sub.module", import_name="TopLevelClass"
        )

    @pytest.mark.parametrize(
        "src", ["type alias_name = int", "alias_name: TypeAlias = int"]
    )
    def test_type_alias(self, module_factory, src):
        module_path = module_factory(src=src, module_name="sub.module")
        imports = TypeCollector.collect(file=module_path)
        assert len(imports) == 1
        assert imports == {
            "sub.module.alias_name": KnownImport(
                import_path="sub.module", import_name="alias_name"
            )
        }

    @pytest.mark.parametrize(
        "src",
        [
            "assign_name = 3",
            "assign_name: int",
            "assign_name: int = 3",
            "assign_name = int",  # Valid type alias, but not supported (yet)
            "assign_name: TypeAlias",  # No value, so should be ignored as a target
        ],
    )
    def test_ignores_assigns(self, module_factory, src):
        module_path = module_factory(src=src, module_name="sub.module")
        imports = TypeCollector.collect(file=module_path)
        assert len(imports) == 0


class Test_TypesDatabase:
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
        db = TypesDatabase(known_imports=self.known_imports.copy())

        annotation, known_import = db.query(name)

        if exp_annotation is None and exp_import_line is None:
            assert exp_annotation is annotation
            assert exp_import_line is known_import
        else:
            assert str(known_import) == exp_import_line
            assert annotation.startswith(known_import.target)
            assert annotation == exp_annotation
    # fmt: on
