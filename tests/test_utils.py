import os
from pathlib import Path

from docstub import _utils


def _create_dummy_package(root: Path, structure: list[str]) -> None:
    """Create a dummy Python package in `root` based on subpaths in `structure`."""
    for item in structure:
        path = root / item
        if item.endswith(".py"):
            path.touch()
        else:
            path.mkdir()


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
        _create_dummy_package(tmp_path, structure)

        assert _utils.module_name_from_path(tmp_path / "foo/__init__.py") == "foo"
        assert _utils.module_name_from_path(tmp_path / "foo/bar.py") == "foo.bar"
        assert (
            _utils.module_name_from_path(tmp_path / "foo/baz/__init__.py") == "foo.baz"
        )
        assert (
            _utils.module_name_from_path(tmp_path / "foo/baz/qux.py") == "foo.baz.qux"
        )

    def test_relative_path(self, tmp_path_cwd):
        structure = [
            "foo/",
            "foo/__init__.py",
            "foo/bar.py",
            "foo/baz/",
            "foo/baz/__init__.py",
            "foo/baz/bar.py",
        ]
        _create_dummy_package(tmp_path_cwd, structure)
        os.chdir(tmp_path_cwd / "foo")
        cwd = Path()

        assert _utils.module_name_from_path(cwd / "__init__.py") == "foo"
        assert _utils.module_name_from_path(cwd / "bar.py") == "foo.bar"

        # `./__init__.py` and `./bar.py` should return different results in
        # different working directories
        os.chdir(tmp_path_cwd / "foo/baz")
        assert _utils.module_name_from_path(cwd / "__init__.py") == "foo.baz"
        assert _utils.module_name_from_path(cwd / "bar.py") == "foo.baz.bar"


def test_pyfile_checksum(tmp_path):
    # Create package
    package_dir = tmp_path / "mypackage"
    package_dir.mkdir()
    package_init = package_dir / "__init__.py"
    package_init.touch()

    # Create submodule to be checked
    submodule_name = "submodule.py"
    submodule_path = package_dir / submodule_name
    with submodule_path.open("w") as fp:
        fp.write("# First line\n")

    original_key = _utils.pyfile_checksum(submodule_path)
    # Check that the key is stable
    assert original_key == _utils.pyfile_checksum(submodule_path)

    # Key changes if content changes
    with submodule_path.open("a") as fp:
        fp.write("# Second line\n")
    changed_content_key = _utils.pyfile_checksum(submodule_path)
    assert original_key != changed_content_key

    # Key changes if qualname / path of module changes
    new_package_dir = package_dir.rename(tmp_path / "newpackage")
    qualname_changed_key = _utils.pyfile_checksum(new_package_dir / submodule_name)
    assert qualname_changed_key != changed_content_key
