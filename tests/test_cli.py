"""Test command line interface."""

import logging
import multiprocessing
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest
from click.testing import CliRunner

from docstub import _cli
from docstub._cache import create_cache

PROJECT_ROOT = Path(__file__).parent.parent


# Trying to run docstub via subprocess fails on Linux pre 3.14 with the
# following:
#
#   RuntimeError: A SemLock created in a fork context is being shared with a
#   process in a spawn context. This is not supported. Please use the same
#   context to create multiprocessing objects and Process.
#
# I think this is because docstub defaults to the more robust method "spawn"
# to create processes. This seems incompatible with the default "fork" method
# on Linux on Python 3.12 & 3.13. Python 3.14 switched to "forkserver" which
# seems fine. I didn't manage to figure out a good way around this other than
# to skip.
skip_if_process_start_defaults_fork = pytest.mark.skipif(
    multiprocessing.get_start_method() == "fork",
    reason="incompatible default OS process start method",
)


class Test_run:
    def test_no_cache(self, tmp_path_cwd, caplog):
        caplog.set_level(logging.INFO)

        source_file = tmp_path_cwd / "some_file.py"
        source_file.touch()

        # First run using '--no-cache' shouldn't create a cache directory
        runner = CliRunner()
        run_result = runner.invoke(_cli.run, args=["--no-cache", str(source_file)])
        assert run_result.exception is None
        assert run_result.exit_code == 0
        assert not _cli._cache_dir_in_cwd().exists()

        # Second run without '--no-cache' should create a cache directory
        caplog.clear()
        runner = CliRunner()
        run_result = runner.invoke(_cli.run, args=[str(source_file)])
        assert run_result.exception is None
        assert run_result.exit_code == 0
        assert _cli._cache_dir_in_cwd().exists()
        # Check that no collected file was logged as "(cached)"
        assert "cached" not in "\n".join(caplog.messages)

        # Third run with existing cache should use cache
        caplog.clear()
        runner = CliRunner()
        run_result = runner.invoke(_cli.run, args=[str(source_file)])
        assert run_result.exception is None
        assert run_result.exit_code == 0
        # Check that at least one collected file was logged as "(cached)"
        assert "cached" in "\n".join(caplog.messages)

        # Fourth run with '--no-cache' should ignore existing cache
        caplog.clear()
        runner = CliRunner()
        run_result = runner.invoke(_cli.run, args=["--no-cache", str(source_file)])
        assert run_result.exception is None
        assert run_result.exit_code == 0
        # Check that at least one collected file was logged as "(cached)"
        assert "cached" not in "\n".join(caplog.messages)

    @skip_if_process_start_defaults_fork
    @pytest.mark.slow
    @pytest.mark.parametrize("workers", [1, 2])
    def test_fail_on_warning(self, workers, tmp_path_cwd):
        source_with_warning = dedent(
            '''
            def foo(x: str):
                """
                Parameters
                ----------
                x : int
                """
            '''
        )
        package = tmp_path_cwd / "src/sample_package"
        package.mkdir(parents=True)
        init_py = package / "__init__.py"
        with init_py.open("x") as io:
            io.write(source_with_warning)

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "docstub",
                "run",
                "--quiet",
                "--quiet",
                "--fail-on-warning",
                "--workers",
                str(workers),
                str(package),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1

    @skip_if_process_start_defaults_fork
    @pytest.mark.slow
    @pytest.mark.parametrize("workers", [1, 2])
    def test_no_output_exit_code(self, workers, tmp_path_cwd):
        faulty_source = dedent(
            '''
            def foo(x):
                """
                Parameters
                ----------
                x : doctype with syntax error
                """
            '''
        )
        package = tmp_path_cwd / "src/sample_package"
        package.mkdir(parents=True)
        init_py = package / "__init__.py"
        with init_py.open("x") as io:
            io.write(faulty_source)

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "docstub",
                "run",
                "--quiet",
                "--quiet",
                "--workers",
                str(workers),
                str(package),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.stdout == ""
        assert result.stderr == ""
        assert result.returncode == 1


class Test_clean:
    @pytest.mark.parametrize("verbosity", [["-v"], ["--verbose"], []])
    def test_basic(self, tmp_path_cwd, verbosity):
        # Cleaning empty directory works
        runner = CliRunner()
        run_result = runner.invoke(_cli.clean, args=verbosity)
        assert run_result.exception is None
        assert run_result.exit_code == 0

        cache_dir = _cli._cache_dir_in_cwd()
        create_cache(cache_dir)
        assert cache_dir.is_dir()

        # Cache directory should be removed after running clean again
        run_result = runner.invoke(_cli.clean, args=verbosity)
        assert run_result.exception is None
        assert run_result.exit_code == 0
        assert not cache_dir.exists()

    def test_corrupted_cache(self, tmp_path_cwd, caplog):
        cache_dir = tmp_path_cwd / ".docstub_cache"
        cache_dir.mkdir()

        runner = CliRunner()
        run_result = runner.invoke(_cli.clean, args=[])
        assert run_result.exit_code == 1
        assert "might not be a valid cache or might be corrupted" in "\n".join(
            caplog.messages
        )
        assert cache_dir.is_dir()
