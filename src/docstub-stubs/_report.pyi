# File generated with docstub

import dataclasses
import logging
from collections.abc import Hashable, Iterator, Mapping, Sequence
from pathlib import Path
from textwrap import indent
from typing import Any, ClassVar, Literal, Self, TextIO

import click

from ._cli_help import should_strip_ansi
from ._utils import naive_natsort_key

logger: logging.Logger

@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class ContextReporter:

    logger: logging.Logger
    path: Path | None = ...
    line: int | None = ...

    def copy_with(
        self,
        *,
        logger: logging.Logger | None = ...,
        path: Path | None = ...,
        line: int | None = ...,
        line_offset: int | None = ...
    ) -> Self: ...
    def report(
        self,
        short: str,
        *args: Any,
        log_level: int,
        details: str | tuple[Any, ...] | None = ...,
        **log_kw: Any
    ) -> None: ...
    def debug(
        self,
        short: str,
        *args: Any,
        details: str | tuple[Any, ...] | None = ...,
        **log_kw: Any
    ) -> None: ...
    def info(
        self,
        short: str,
        *args: Any,
        details: str | tuple[Any, ...] | None = ...,
        **log_kw: Any
    ) -> None: ...
    def warn(
        self,
        short: str,
        *args: Any,
        details: str | tuple[Any, ...] | None = ...,
        **log_kw: Any
    ) -> None: ...
    def error(
        self,
        short: str,
        *args: Any,
        details: str | tuple[Any, ...] | None = ...,
        **log_kw: Any
    ) -> None: ...
    def critical(
        self,
        short: str,
        *args: Any,
        details: str | tuple[Any, ...] | None = ...,
        **log_kw: Any
    ) -> None: ...
    def __post_init__(self) -> None: ...
    @staticmethod
    def underline(line: str, *, char: str = ...) -> str: ...

class ReportHandler(logging.StreamHandler):
    group_errors: bool
    error_count: int
    warning_count: int

    level_to_color: ClassVar[dict[int, str]]

    def __init__(
        self, stream: TextIO | None = ..., group_errors: bool = ...
    ) -> None: ...
    def format(self, record: logging.LogRecord) -> str: ...
    def handle(self, record: logging.LogRecord) -> bool: ...
    def emit_grouped(self) -> None: ...

class LogCounter(logging.NullHandler):
    critical_count: int
    error_count: int
    warning_count: int

    def __init__(self) -> None: ...
    def handle(self, record: logging.LogRecord) -> bool: ...

def setup_logging(
    *, verbosity: Literal[-2, -1, 0, 1, 2, 3], group_errors: bool
) -> tuple[ReportHandler, LogCounter]: ...
def update_with_add_values(
    *mappings: Mapping[Hashable, int | Sequence], out: dict | None = ...
) -> dict: ...

class Stats(Mapping):
    class _UNSET:
        pass

    def __init__(self, stats: dict[str, list[Any] | str] | None = ...) -> None: ...
    def __getitem__(self, key: str) -> list[Any] | int: ...
    def __iter__(self) -> Iterator: ...
    def __len__(self) -> int: ...
    def inc_counter(self, key: str, *, inc: int = ...) -> None: ...
    def append_to_list(self, key: str, value: Any) -> None: ...
    @classmethod
    def merge(cls, *stats: Self) -> Self: ...
    def __repr__(self) -> str: ...
    def pop(self, key: str, *, default: Any = ...) -> list[Any] | int: ...
    def pop_all(self) -> dict[str, list[Any] | int]: ...
