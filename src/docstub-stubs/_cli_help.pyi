# File generated with docstub

import logging
import os
import re
from collections.abc import Sequence
from typing import IO, Any, ClassVar

import click
from click.formatting import iter_rows, measure_table, wrap_text

logger: logging.Logger

try:
    from click._compat import should_strip_ansi as _click_should_strip_ansi

except Exception:

    def _click_should_strip_ansi(
        stream: IO[Any] | None = ..., color: bool | None = ...
    ) -> bool: ...

def should_strip_ansi(
    stream: IO[Any] | None = ..., color: bool | None = ...
) -> bool: ...

class HelpFormatter(click.formatting.HelpFormatter):
    strip_ansi: bool

    rule_defs: ClassVar[dict[str, tuple[str, str]]]

    def __init__(self, *args: Any, **kwargs: Any) -> None: ...
    def write_dl(
        self,
        rows: Sequence[tuple[str, str]],
        *args: Any,
        **kwargs: Any,
    ) -> None: ...
    def write_heading(self, heading: str) -> None: ...
    def write_usage(
        self, prog: str, args: str = ..., prefix: str | None = ...
    ) -> None: ...
    def _highlight_last(self, *, n: int, rules: list[str]) -> None: ...
    def _highlight(self, string: str, *, rules: list[str]) -> str: ...
