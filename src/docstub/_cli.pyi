# File generated with docstub

import logging
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Literal

import click

from ._analysis import PyImport
from ._config import Config

logger: logging.Logger

def _cache_dir_in_cwd() -> Path: ...
def _load_configuration(config_paths: list[Path] | None = ...) -> Config: ...
def _calc_verbosity(
    *, verbose: Literal[0, 1, 2], quiet: Literal[0, 1, 2]
) -> Literal[-2, -1, 0, 1, 2]: ...
def _collect_type_info(
    root_path: Path, *, ignore: Sequence[str] = ..., cache: bool = ...
) -> tuple[dict[str, PyImport], dict[str, PyImport]]: ...
def _format_unknown_names(unknown_names: Iterable[str]) -> str: ...
def log_execution_time() -> None: ...
@click.group()
def cli() -> None: ...
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
