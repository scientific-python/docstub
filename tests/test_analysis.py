from textwrap import dedent

import pytest

from docstub._analysis import (
    PyImport,
    TypeCollector,
    TypeMatcher,
)


class Test_KnownImport:
    def test_dot_in_alias(self):
        with pytest.raises(ValueError, match=r".*can't contain a '\.'"):
            PyImport(import_="foo.bar.baz", as_="bar.baz")


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
        types, prefixes = TypeCollector.collect(file=module_path)
        assert prefixes == {}
        assert len(types) == 2
        assert types["sub.module.TopLevelClass"] == PyImport(
            from_="sub.module", import_="TopLevelClass"
        )
        # The import for the nested class should still use only the top-level
        # class as an import target
        assert types["sub.module.TopLevelClass.NestedClass"] == PyImport(
            from_="sub.module", import_="TopLevelClass"
        )

    @pytest.mark.parametrize(
        "src", ["type alias_name = int", "alias_name: TypeAlias = int"]
    )
    def test_type_alias(self, module_factory, src):
        module_path = module_factory(src=src, module_name="sub.module")
        types, prefixes = TypeCollector.collect(file=module_path)
        assert prefixes == {}
        assert len(types) == 1
        assert types == {
            "sub.module.alias_name": PyImport(from_="sub.module", import_="alias_name")
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
        types, prefixes = TypeCollector.collect(file=module_path)
        assert prefixes == {}
        assert len(types) == 0

    def test_from_import(self, module_factory):
        src = dedent(
            """
            from calendar import gregorian
            from calendar.gregorian import August as Aug, December
            """
        )

        module_path = module_factory(src=src, module_name="sub.module")
        types, prefixes = TypeCollector.collect(file=module_path)

        assert prefixes == {}
        assert types == {
            "calendar.gregorian": PyImport(from_="calendar", import_="gregorian"),
            "calendar.gregorian.August": PyImport(
                from_="calendar.gregorian", import_="August"
            ),
            "calendar.gregorian.December": PyImport(
                from_="calendar.gregorian", import_="December"
            ),
            "sub.module:gregorian": PyImport(implicit="sub.module:gregorian"),
            "sub.module:Aug": PyImport(implicit="sub.module:Aug"),
            "sub.module:December": PyImport(implicit="sub.module:December"),
        }

    def test_relative_import(self, module_factory):
        src = dedent(
            """
            from . import January
            from .. import August as Aug, December
            from ..calendar import September
            """
        )
        module_path = module_factory(src=src, module_name="sub.module")
        types, prefixes = TypeCollector.collect(file=module_path)
        assert prefixes == {}
        assert types == {
            "sub.module:January": PyImport(implicit="sub.module:January"),
            "sub.module:Aug": PyImport(implicit="sub.module:Aug"),
            "sub.module:December": PyImport(implicit="sub.module:December"),
            "sub.module:September": PyImport(implicit="sub.module:September"),
        }

    def test_imports(self, module_factory):
        src = dedent(
            """
            import calendar
            import drinks as dr
            import calendar.gregorian as greg
            """
        )

        module_path = module_factory(src=src, module_name="sub.module")
        types, prefixes = TypeCollector.collect(file=module_path)
        assert types == {}
        assert len(prefixes) == 3
        assert prefixes == {
            "sub.module:calendar": PyImport(implicit="sub.module:calendar"),
            "sub.module:dr": PyImport(implicit="sub.module:dr"),
            "sub.module:greg": PyImport(implicit="sub.module:greg"),
        }


class Test_TypeMatcher:
    type_prefixes = {
        "np": PyImport(import_="numpy", as_="np"),
        "foo.bar.Baz": PyImport(from_="foo.bar", import_="Baz"),
    }

    types = {
        "dict": PyImport(implicit="dict"),
        "foo.bar": PyImport(from_="foo", import_="bar"),
        "foo.bar.Baz": PyImport(from_="foo.bar", import_="Baz"),
        "foo.bar.Baz.Bix": PyImport(from_="foo.bar", import_="Baz"),
        "foo.bar.Baz.Qux": PyImport(from_="foo", import_="bar"),
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

        type_name, py_import = db.match(search_name)

        if expected_name is None and expected_origin is None:
            assert expected_name is type_name
            assert expected_origin is py_import
        else:
            assert type_name is not None
            assert py_import is not None
            assert str(py_import) == expected_origin
            assert type_name.startswith(py_import.target)
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

        type_name, py_import = db.match(search_name)

        if expected_name is None and expected_origin is None:
            assert expected_name is type_name
            assert expected_origin is py_import
        else:
            assert type_name is not None
            assert py_import is not None
            assert str(py_import) == expected_origin
            assert type_name.startswith(py_import.target)
            assert type_name == expected_name
    # fmt: on

    @pytest.mark.parametrize(
        ("search_name", "import_path"),
        [
            ("Iterable", "collections.abc"),
            ("collections.abc.Iterable", "collections.abc"),
            ("Literal", "typing"),
            ("typing.Literal", "typing"),
            ("NoneType", "types"),
            ("SimpleNamespace", "types"),
        ],
    )
    def test_common_known_types(self, search_name, import_path):
        matcher = TypeMatcher()
        type_name, py_import = matcher.match(search_name)

        assert type_name == search_name.split(".")[-1]
        assert py_import is not None
        assert py_import.from_ == import_path

    def test_scoped_types(self, module_factory):
        types = {
            "sub.module:January": PyImport(implicit="sub.module:January"),
        }
        matcher = TypeMatcher(types=types)

        # Shouldn't match because the current module isn't set
        type_name, py_import = matcher.match("January")
        assert type_name is None
        assert py_import is None

        # Set current module to something that doesn't match scope
        module_path = module_factory(src="", module_name="other.module")
        matcher.current_file = module_path
        # Still shouldn't match because the current module doesn't match the scope
        type_name, py_import = matcher.match("January")
        assert type_name is None
        assert py_import is None

        # Set current module to match the scope
        module_path = module_factory(src="", module_name="sub.module")
        matcher.current_file = module_path
        # Now we should find the type
        type_name, py_import = matcher.match("January")
        assert type_name == "January"
        assert py_import == PyImport(implicit="sub.module:January")

    def test_scoped_type_prefix(self, module_factory):
        type_prefixes = {
            "sub.module:cal": PyImport(implicit="sub.module:cal"),
        }
        matcher = TypeMatcher(type_prefixes=type_prefixes)

        # Shouldn't match because the current module isn't set
        type_name, py_import = matcher.match("cal.January")
        assert type_name is None
        assert py_import is None

        # Set current module to something that doesn't match scope
        module_path = module_factory(src="", module_name="other.module")
        matcher.current_file = module_path
        # Still shouldn't match because the current module doesn't match the scope
        type_name, py_import = matcher.match("cal.January")
        assert type_name is None
        assert py_import is None

        # Set current module to match the scope
        module_path = module_factory(src="", module_name="sub.module")
        matcher.current_file = module_path
        # Now we should find the prefix
        type_name, py_import = matcher.match("cal.January")
        assert type_name == "cal.January"
        assert py_import == PyImport(implicit="sub.module:cal")

    def test_nicknames(self, caplog):
        types = {
            "Buffer": PyImport(from_="collections.abc", import_="Buffer"),
        }
        type_nicknames = {
            "buffer": "collections.abc.Buffer",
        }
        matcher = TypeMatcher(types=types, type_nicknames=type_nicknames)

        type_name, py_import = matcher.match("buffer")
        assert type_name == "Buffer"
        assert py_import == PyImport(from_="collections.abc", import_="Buffer")

    def test_nested_nicknames(self, caplog):
        types = {
            "Foo": PyImport(implicit="Foo"),
            "Bar": PyImport(implicit="Bar"),
        }
        type_nicknames = {
            "Foo": "~.Baz",
            "~.Baz": "B.i.k",
            "B.i.k": "Bar",
        }
        matcher = TypeMatcher(types=types, type_nicknames=type_nicknames)

        type_name, py_import = matcher.match("Foo")
        assert type_name == "Bar"
        assert py_import == PyImport(implicit="Bar")

    def test_nickname_infinite_loop(self, caplog):
        types = {
            "Foo": PyImport(implicit="Foo"),
            "Bar": PyImport(implicit="Bar"),
        }
        type_nicknames = {
            "Foo": "Bar",
            "Bar": "Foo",
        }
        matcher = TypeMatcher(types=types, type_nicknames=type_nicknames)

        type_name, py_import = matcher.match("Foo")
        assert len(caplog.records) == 1
        assert "Reached limit while resolving nicknames" in caplog.text

        assert type_name == "Foo"
        assert py_import == PyImport(implicit="Foo")
