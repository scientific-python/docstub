# File generated with docstub

import logging
import time
from collections import Counter
from collections.abc import Iterable, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from ._analysis import PyImport, TypeCollector, TypeMatcher, common_known_types
from ._cache import CACHE_DIR_NAME, FileCache
from ._concurrency import LoggingProcessExecutor, guess_concurrency_params
from ._config import Config
from ._path_utils import (
    STUB_HEADER_COMMENT,
    find_package_root,
    walk_source_and_targets,
    walk_source_package,
)
from ._report import setup_logging
from ._stubs import Py2StubTransformer, try_format_stub
from ._utils import update_with_add_values
from ._version import __version__

logger: logging.Logger

def cache_dir_in_cwd() -> Path: ...
def _load_configuration(config_paths: list[Path] | None = ...) -> Config: ...
def _collect_type_info(
    root_path: Path, *, ignore: Sequence[str] = ..., cache: bool = ...
) -> tuple[dict[str, PyImport], dict[str, PyImport]]: ...
def _log_execution_time() -> None: ...
def _format_unknown_names(names: Iterable[str]) -> str: ...
def _generate_single_stub(
    task: tuple[Path, Path, Py2StubTransformer],
) -> dict[str, int | list[str]]: ...
def generate_stubs(
    *,
    root_path: Path,
    out_dir: Path,
    config_paths: Sequence[Path],
    ignore: Sequence[str],
    group_errors: bool,
    allow_errors: int,
    fail_on_warning: bool,
    desired_worker_count: int,
    no_cache: bool,
    verbosity: Literal[-2, -1, 0, 1, 2, 3],
) -> Literal[0, 1]: ...
