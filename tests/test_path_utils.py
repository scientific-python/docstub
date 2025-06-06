from docstub._path_utils import walk_python_package


class Test_walk_python_package:
    def test_ignore(self, tmp_path):
        top_script = tmp_path / "script.py"
        top_script.touch()
        sub_package = tmp_path / "sub_package"
        sub_package.mkdir()
        sub_init = sub_package / "__init__.py"
        sub_init.touch()
        module_in_dir = sub_package / "module_in_dir.py"
        module_in_dir.touch()

        paths = set(walk_python_package(tmp_path))
        assert paths == {top_script, sub_init, module_in_dir}

        paths = set(walk_python_package(tmp_path, ignore=["**/*.py"]))
        assert paths == set()

        paths = set(
            walk_python_package(tmp_path, ignore=["**/module*", "**/script.py"])
        )
        assert paths == {sub_init}

        paths = set(walk_python_package(tmp_path, ignore=["**/sub_package"]))
        assert paths == {top_script}

        paths = set(walk_python_package(tmp_path, ignore=["**/*init*"]))
        assert paths == {top_script, module_in_dir}
