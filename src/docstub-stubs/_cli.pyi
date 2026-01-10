# File generated with docstub

import logging
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Literal

import click
from _typeshed import Incomplete

from ._cli_help import HelpFormatter
from ._version import __version__

logger: logging.Logger

click.Context.formatter_class = HelpFormatter

@click.group()
def cli() -> None: ...
def _calc_verbosity(
    *, verbose: Literal[0, 1, 3], quiet: Literal[0, 1, 2]
) -> Literal[-2, -1, 0, 1, 2, 3]: ...
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
    desired_worker_count: int,
    no_cache: bool,
    verbose: int,
    quiet: int,
) -> None: ...
@cli.command()
def clean(verbose: int, quiet: int) -> None: ...
