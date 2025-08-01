"""Test command line interface."""

import logging
import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from docstub import _cli
from docstub._cache import create_cache

PROJECT_ROOT = Path(__file__).parent.parent


@pytest.fixture
def tmp_path_cwd(tmp_path):
    """Fixture: Create temporary directory and use it as working directory.

    .. warning::
        Not written with parallelization in mind!
    """
    previous_cwd = Path.cwd()
    os.chdir(tmp_path)
    try:
        yield tmp_path
    except:
        os.chdir(previous_cwd)
        raise


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
        assert "(cached)" not in "\n".join(caplog.messages)

        # Third run with existing cache should use cache
        caplog.clear()
        runner = CliRunner()
        run_result = runner.invoke(_cli.run, args=[str(source_file)])
        assert run_result.exception is None
        assert run_result.exit_code == 0
        # Check that at least one collected file was logged as "(cached)"
        assert "(cached)" in "\n".join(caplog.messages)

        # Fourth run with '--no-cache' should ignore existing cache
        caplog.clear()
        runner = CliRunner()
        run_result = runner.invoke(_cli.run, args=["--no-cache", str(source_file)])
        assert run_result.exception is None
        assert run_result.exit_code == 0
        # Check that at least one collected file was logged as "(cached)"
        assert "(cached)" not in "\n".join(caplog.messages)


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
