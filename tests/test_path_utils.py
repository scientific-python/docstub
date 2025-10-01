from pathlib import Path

import pytest

from docstub._path_utils import STUB_HEADER_COMMENT, walk_source_package


class Test_walk_source_package:
    def test_single_file(self, tmp_path):
        top_script = tmp_path / "script.py"
        top_script.touch()

        paths = sorted(walk_source_package(top_script))
        assert paths == [top_script]

    def test_single_stub_precedence(self, tmp_path):
        # Check that alternate stub file takes precedence
        top_script = tmp_path / "script.py"
        top_script.touch()
        top_stub = tmp_path / "script.pyi"
        top_stub.touch()

        paths = sorted(walk_source_package(top_script))
        assert paths == [top_stub]

    def test_single_stub(self, tmp_path):
        top_stub = tmp_path / "script.pyi"
        top_stub.touch()
        paths = sorted(walk_source_package(top_stub))
        assert paths == [top_stub]

    def test_package_stub(self, tmp_path):
        init_py = tmp_path / "__init__.py"
        init_py.touch()
        init_stub = tmp_path / "__init__.pyi"
        init_stub.touch()
        script_py = tmp_path / "_version.py"
        script_py.touch()
        script_stub = tmp_path / "_version.pyi"
        script_stub.touch()

        paths = sorted(walk_source_package(tmp_path))
        assert paths == [init_stub, script_stub]

    def test_not_a_package(self, tmp_path):
        top_script = tmp_path / "script.py"
        top_script.touch()

        with pytest.raises(TypeError, match=r".* must be a Python file or package"):
            next(walk_source_package(tmp_path))

    def test_single_with_docstub_generated_stub(self, tmp_path):
        script_py = tmp_path / "script.py"
        script_py.touch()
        script_stub = tmp_path / "script.pyi"
        with script_stub.open("w") as io:
            io.write(STUB_HEADER_COMMENT)

        paths = sorted(walk_source_package(script_py))
        assert paths == [script_py]

    def test_package_with_docstub_generated_stub(self, tmp_path):
        init_py = tmp_path / "__init__.py"
        init_py.touch()
        init_stub = tmp_path / "__init__.pyi"
        with init_stub.open("w") as io:
            io.write(STUB_HEADER_COMMENT)

        paths = sorted(walk_source_package(tmp_path))
        assert paths == [init_py]

    @pytest.mark.parametrize("name", ["script.py", "script.pyi"])
    def test_ignore_single_file(self, tmp_path, name):
        top_stub = tmp_path / name
        top_stub.touch()
        paths = sorted(walk_source_package(top_stub, ignore=name))
        assert paths == []

    def test_ignore_pyi(self, tmp_path):
        for name in ("__init__.py", "script.py"):
            (tmp_path / name).touch()
            (tmp_path / name).with_suffix(".pyi").touch()
            (tmp_path / "sub").mkdir(exist_ok=True)
            (tmp_path / "sub" / name).touch()
            (tmp_path / "sub" / name).with_suffix(".pyi").touch()

        paths = sorted(walk_source_package(tmp_path))
        assert len(paths) == 4

        paths = sorted(walk_source_package(tmp_path, ignore="*.pyi"))
        assert paths == []

        paths = sorted(walk_source_package(tmp_path, ignore="**/*.pyi"))
        assert paths == []

    def test_ignore(self, tmp_path):
        top_init = tmp_path / "__init__.py"
        top_init.touch()
        sub_package = tmp_path / "sub_package"
        sub_package.mkdir()
        sub_init = sub_package / "__init__.py"
        sub_init.touch()
        module_in_sub_package = sub_package / "module_in_sub_package.py"
        module_in_sub_package.touch()
        stub_in_sub_package = sub_package / "module_in_sub_package.pyi"
        stub_in_sub_package.touch()

        paths = sorted(walk_source_package(tmp_path))
        assert paths == [top_init, sub_init, stub_in_sub_package]

        paths = sorted(walk_source_package(tmp_path, ignore=["**/*.py"]))
        assert paths == [stub_in_sub_package]

        paths = sorted(walk_source_package(tmp_path, ignore=["**/*.py*"]))
        assert paths == []

        paths = sorted(
            walk_source_package(tmp_path, ignore=["**/module*", "__init__.py"])
        )
        assert paths == [sub_init]

        paths = sorted(walk_source_package(tmp_path, ignore=["**/sub_package"]))
        assert paths == [top_init]

        paths = sorted(walk_source_package(tmp_path, ignore=["**/*init*"]))
        assert paths == [stub_in_sub_package]

    def test_ignore_relative_path(self, tmp_path_cwd):
        init = tmp_path_cwd / "__init__.py"
        init.touch()
        tests_dir = tmp_path_cwd / "tests"
        tests_dir.mkdir()
        sub_init = tests_dir / "__init__.py"
        sub_init.touch()

        relative_cwd = Path()

        paths = sorted(walk_source_package(relative_cwd))
        assert [p.resolve() for p in paths] == [init, sub_init]
        paths = sorted(walk_source_package(relative_cwd, ignore=["**/tests"]))
        assert [p.resolve() for p in paths] == [init]
