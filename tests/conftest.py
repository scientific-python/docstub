import os
from pathlib import Path

import pytest


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
