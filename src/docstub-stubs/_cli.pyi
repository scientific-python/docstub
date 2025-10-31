# File generated with docstub

import logging
import shutil
import sys
import time
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

import click

from ._analysis import PyImport, TypeCollector, TypeMatcher, common_known_types
from ._cache import CACHE_DIR_NAME, FileCache, validate_cache
from ._cli_help import HelpFormatter
from ._config import Config
from ._path_utils import (
    STUB_HEADER_COMMENT,
    find_package_root,
    walk_source_and_targets,
    walk_source_package,
)
from ._report import setup_logging
from ._stubs import Py2StubTransformer, try_format_stub
from ._version import __version__

logger: logging.Logger

def _cache_dir_in_cwd() -> Path: ...
def _load_configuration(config_paths: list[Path] | None = ...) -> Config: ...
def _calc_verbosity(
    *, verbose: Literal[0, 1, 3], quiet: Literal[0, 1, 2]
) -> Literal[-2, -1, 0, 1, 2, 3]: ...
def _collect_type_info(
    root_path: Path, *, ignore: Sequence[str] = ..., cache: bool = ...
) -> tuple[dict[str, PyImport], dict[str, PyImport]]: ...
def _format_unknown_names(names: Iterable[str]) -> str: ...
def log_execution_time() -> None: ...

click.Context.formatter_class: click.formatting.HelpFormatter

@click.group()
def cli() -> None: ...
def _add_verbosity_options(func: Callable) -> Callable: ...
@cli.command()
def run(
    *,
    root_path: Path,
    out_dir: Path,
    config_paths: Sequence[Path],
    ignore: Sequence[str],
    group_errors: bool,
    allow_errors: int,
    fail_on_warning: bool,
    no_cache: bool,
    verbose: int,
    quiet: int,
) -> None: ...
@cli.command()
def clean(verbose: int, quiet: int) -> None: ...
