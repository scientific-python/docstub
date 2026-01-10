import logging
import os
import re

import click
from click.formatting import iter_rows, measure_table, wrap_text

logger: logging.Logger = logging.getLogger(__name__)


# Be defensive about using click's non-public `should_strip_ansi`
try:
    from click._compat import (
        should_strip_ansi as _click_should_strip_ansi,
    )

except Exception:
    logger.exception("Unexpected error while using click's `should_strip_ansi`")

    def _click_should_strip_ansi(stream=None, color=None):
        """
        Parameters
        ----------
        stream : IO[Any], optional
        color : bool, optional

        Returns
        -------
        should_strip : bool
        """
        return True


def should_strip_ansi(stream=None, color=None):
    """

    Parameters
    ----------
    stream : IO[Any], optional
    color : bool, optional

    Returns
    -------
    should_strip : bool
    """
    # Respect https://no-color.org
    NO_COLOR_ENV = os.getenv("NO_COLOR", "").lower() not in ("0", "false", "no", "")
    return NO_COLOR_ENV or _click_should_strip_ansi(stream, color)


class HelpFormatter(click.formatting.HelpFormatter):
    """Custom help formatter for click.

    Attributes
    ----------
    rule_defs : ClassVar[dict of {str: tuple[str, str]}]
    strip_ansi : bool
        Defaults to :func:`should_strip_ansi()`.

    Examples
    --------
    To use this formatter with click:

    >>> import click
    >>> click.Context.formatter_class = HelpFormatter  # doctest: +SKIP
    """

    rule_defs = {
        "dl-command": (
            r"(\n  |^  )(\w[\w-]+)(?=  )",
            r"\1" + click.style(r"\g<2>", bold=True, fg="magenta"),
        ),
        "short-opt": (r" -\w+\b", click.style(r"\g<0>", bold=True, fg="red")),
        "long-opt": (r" --\w[\w-]+\b", click.style(r"\g<0>", bold=True, fg="magenta")),
        "dl-opt-arg": (r"(?<!-)\b[A-Z_]+", click.style(r"\g<0>", fg="magenta")),
        "heading": (r"[^:]+:", click.style(r"\g<0>", bold=True)),
    }

    def __init__(self, *args, **kwargs):
        """
        Parameters
        ----------
        *args, **kwargs : Any
        """
        super().__init__(*args, **kwargs)
        self.strip_ansi = should_strip_ansi()

    def write_dl(
        self,
        rows,
        *args,
        **kwargs,
    ):
        """Print definition list.

        Parameters
        ----------
        rows : Sequence[tuple[str, str]]
        *args, **kwargs : Any
        """
        if not rows[0][0].strip().startswith("-"):
            dl_start = len(self.buffer)
            super().write_dl(rows, *args, **kwargs)
            self._highlight_last(
                n=len(self.buffer) - dl_start,
                rules=["dl-command"],
            )
            return

        # Add intend so options like "-v, --verbose" and "--config" are aligned
        # on the "--"
        rows = [
            (f"    {key}" if key.lstrip().startswith("--") else key, value)
            for key, value in rows
        ]

        rows = list(rows)
        widths = measure_table(rows)
        if len(widths) != 2:
            raise TypeError("Expected two columns for definition list")

        for first, second in iter_rows(rows, len(widths)):
            self.write(f"{'':>{self.current_indent}}{first}")
            self._highlight_last(n=1, rules=["short-opt", "long-opt", "dl-opt-arg"])
            if not second:
                self.write("\n")
                continue

            self.write("\n")
            self.write(" " * (8 + self.current_indent))

            text_width = max(self.width - 8, 10)
            wrapped_text = wrap_text(second, text_width, preserve_paragraphs=True)
            lines = wrapped_text.splitlines()

            if lines:
                self.write(f"{lines[0]}\n")

                for line in lines[1:]:
                    self.write(f"{'':>{8 + self.current_indent}}{line}\n")
            else:
                self.write("\n")

    def write_heading(self, heading):
        """
        Parameters
        ----------
        heading : str
        """
        super().write_heading(heading)
        if not self.strip_ansi:
            self._highlight_last(n=1, rules=["heading"])

    def write_usage(self, prog, args="", prefix=None):
        """
        Parameters
        ----------
        prog : str
        args : str, optional
        prefix : str, optional
        """
        if prefix is None:
            prefix = "Usage: "

        start = len(self.buffer)
        super().write_usage(prog, args, prefix=prefix)

        re_prog = re.escape(prog).replace(r"\ ", r"\s+")
        re_args = re.escape(args).replace(r"\ ", r"\s+")
        re_prefix = re.escape(prefix).replace(r"\ ", r"\s+")

        self._highlight_last(
            n=len(self.buffer) - start,
            rules=[
                (re_prog, click.style(r"\g<0>", bold=True, fg="magenta")),
                (re_args, click.style(r"\g<0>", fg="magenta")),
                (re_prefix, click.style(r"\g<0>", bold=True)),
            ],
        )

    def _highlight_last(self, *, n, rules):
        """Highlight the last `n` elements in the buffer according to `rules`.

        Parameters
        ----------
        n : int
        rules : list[str]
        """
        last = [self.buffer.pop() for _ in range(n)][::-1]
        string = "".join(last)
        string = self._highlight(string, rules=rules)
        self.buffer.append(string)

    def _highlight(self, string, *, rules):
        """Highlight `string` according to `rules`.

        Parameters
        ----------
        string : str
        rules : list[str]

        Returns
        -------
        string : str
        """
        if self.strip_ansi:
            return string

        rules = (
            self.rule_defs[rule] if isinstance(rule, str) else rule for rule in rules
        )
        for pattern, substitute in rules:
            string = re.sub(pattern, substitute, string, flags=re.DOTALL)
        return string
