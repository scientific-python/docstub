from docstub._utils import module_name_from_path


class Test_module_name_from_path:
    def test_basic(self, tmp_path):
        # Package structure
        structure = [
            "foo/",
            "foo/__init__.py",
            "foo/bar.py",
            "foo/baz/",
            "foo/baz/__init__.py",
            "foo/baz/qux.py",
        ]
        for item in structure:
            path = tmp_path / item
            if item.endswith(".py"):
                path.touch()
            else:
                path.mkdir()

        assert module_name_from_path(tmp_path / "foo/__init__.py") == "foo"
        assert module_name_from_path(tmp_path / "foo/bar.py") == "foo.bar"
        assert module_name_from_path(tmp_path / "foo/baz/__init__.py") == "foo.baz"
        assert module_name_from_path(tmp_path / "foo/baz/qux.py") == "foo.baz.qux"
