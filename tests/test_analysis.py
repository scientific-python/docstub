from textwrap import dedent

import pytest

from docstub._analysis import (
    KnownImport,
    StubTypeCollector,
    TypeCollector,
    TypeMatcher,
)


class Test_KnownImport:
    def test_dot_in_alias(self):
        with pytest.raises(ValueError, match=r".*can't contain a '\.'"):
            KnownImport(import_name="foo.bar.baz", import_alias="bar.baz")


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
        assert len(imports) == 4
        assert imports["sub.module:TopLevelClass"] == KnownImport(
            import_path="sub.module", import_name="TopLevelClass"
        )
        assert imports["sub.module.TopLevelClass"] == KnownImport(
            import_path="sub.module", import_name="TopLevelClass"
        )
        # The import for the nested class should still use only the top-level
        # class as an import target
        assert imports["sub.module:TopLevelClass.NestedClass"] == KnownImport(
            import_path="sub.module", import_name="TopLevelClass"
        )
        assert imports["sub.module.TopLevelClass.NestedClass"] == KnownImport(
            import_path="sub.module", import_name="TopLevelClass"
        )

    @pytest.mark.parametrize(
        "src", ["type alias_name = int", "alias_name: TypeAlias = int"]
    )
    def test_type_alias(self, module_factory, src):
        module_path = module_factory(src=src, module_name="sub.module")
        imports = TypeCollector.collect(file=module_path)
        assert len(imports) == 2
        assert imports == {
            "sub.module:alias_name": KnownImport(
                import_path="sub.module", import_name="alias_name"
            ),
            "sub.module.alias_name": KnownImport(
                import_path="sub.module", import_name="alias_name"
            ),
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


class Test_StubTypeCollector:

    def test_debug(self, module_factory):
        module_path = module_factory(
            src=dedent(
                """
                from foo import Bar as Bar
                from baz import (Bix as Bix_, Qux)
                """
            ),
            module_name="sub.module",
        )
        types = StubTypeCollector.collect(file=module_path)


class Test_TypeMatcher:
    type_prefixes = {  # noqa: RUF012
        "np": KnownImport(import_name="numpy", import_alias="np"),
        "foo.bar.Baz": KnownImport(import_path="foo.bar", import_name="Baz"),
    }

    types = {  # noqa: RUF012
        "dict": KnownImport(builtin_name="dict"),
        "foo.bar": KnownImport(import_path="foo", import_name="bar"),
        "foo.bar.Baz": KnownImport(import_path="foo.bar", import_name="Baz"),
        "foo.bar.Baz.Bix": KnownImport(import_path="foo.bar", import_name="Baz"),
        "foo.bar.Baz.Qux": KnownImport(import_path="foo", import_name="bar"),
    }

    # fmt: off
    @pytest.mark.parametrize(
        ("search_name", "expected_name", "expected_origin"),
        [
            ("foo.bar.Baz", "Baz", "from foo.bar import Baz"),
            # Finds "Baz" with abbreviated form as well
            (  "~.bar.Baz", "Baz", "from foo.bar import Baz"),
            (      "~.Baz", "Baz", "from foo.bar import Baz"),

            # Finds nested class "Baz.Bix"
            ("foo.bar.Baz.Bix", "Baz.Bix", "from foo.bar import Baz"),
            (  "~.bar.Baz.Bix", "Baz.Bix", "from foo.bar import Baz"),
            (      "~.Baz.Bix", "Baz.Bix", "from foo.bar import Baz"),
            (          "~.Bix", "Baz.Bix", "from foo.bar import Baz"),

            # Abbreviated form with not explicitly defined class "Baz.Gul"
            # never matches
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
    def test_query_types(self, search_name, expected_name, expected_origin):
        db = TypeMatcher(types=self.types.copy())

        type_name, type_origin = db.match(search_name)

        if expected_name is None and expected_origin is None:
            assert expected_name is type_name
            assert expected_origin is type_origin
        else:
            assert type_name is not None
            assert type_origin is not None
            assert str(type_origin) == expected_origin
            assert type_name.startswith(type_origin.target)
            assert type_name == expected_name
    # fmt: on

    # fmt: off
    @pytest.mark.parametrize(
        ("search_name", "expected_name", "expected_origin"),
        [
            ("np", "np", "import numpy as np"),
            # Finds imports whose import target matches the start of `name`
            ("np.doesnt_exist", "np.doesnt_exist", "import numpy as np"),
            # Finds nested class "Baz.Gul" that's not explicitly defined, but
            # whose import target matches "Baz"
            ("foo.bar.Baz.Gul", "Baz.Gul", "from foo.bar import Baz"),
        ]
    )
    def test_query_prefix(self, search_name, expected_name, expected_origin):
        db = TypeMatcher(type_prefixes=self.type_prefixes.copy())

        type_name, type_origin = db.match(search_name)

        if expected_name is None and expected_origin is None:
            assert expected_name is type_name
            assert expected_origin is type_origin
        else:
            assert type_name is not None
            assert type_origin is not None
            assert str(type_origin) == expected_origin
            assert type_name.startswith(type_origin.target)
            assert type_name == expected_name
    # fmt: on

    @pytest.mark.parametrize(
        ("search_name", "import_path"),
        [
            ("Iterable", "collections.abc"),
            ("collections.abc.Iterable", "collections.abc"),
            ("Literal", "typing"),
            ("typing.Literal", "typing"),
        ],
    )
    def test_common_known_types(self, search_name, import_path):
        matcher = TypeMatcher()
        type_name, type_origin = matcher.match(search_name)

        assert type_name == search_name.split(".")[-1]
        assert type_origin is not None
        assert type_origin.import_path == import_path

    def test_scoped_type(self):
        types = {
            "foo:Bar": KnownImport(import_path="foo", import_name="Bar"),
        }
        matcher = TypeMatcher(types=types)

        type_name, type_origin = matcher.match("Bar")
        assert type_name is None
        assert type_origin is None

        matcher.current_module = "foo"
        type_name, type_origin = matcher.match("Bar")
        assert type_name == "Bar"
        assert type_origin is not None
        assert type_origin.import_path == "foo"
