import dataclasses
import itertools
import re
from pathlib import Path
from textwrap import indent

import click


def accumulate_qualname(qualname, *, start_right=False):
    """Return possible partial names from a fully qualified one.

    Parameters
    ----------
    qualname : str
        A fully qualified name, possibliy delimited by ".".
    start_right : bool, optional
        By default, dot-delimited names in `qualname` are accumulated by starting with
        the first name and then appending following names successively. If true instead,
        the accumulation happens in reverse order: the last name is prepended with
        previous names successively.

    Examples
    --------
    >>> accumulate_qualname("a.b.c")
    ('a', 'a.b', 'a.b.c')
    >>> accumulate_qualname("a.b.c", start_right=True)
    ('c', 'b.c', 'a.b.c')
    """
    fragments = qualname.split(".")
    if start_right is True:
        fragments = reversed(fragments)
        template = "{1}.{0}"
    else:
        template = "{0}.{1}"
    out = tuple(
        itertools.accumulate(fragments, func=lambda x, y: template.format(x, y))
    )
    return out


def escape_qualname(name):
    """Format a string such that it can be used as a valid Python variable.

    Parameters
    ----------
    name : str

    Returns
    -------
    qualname : str

    Examples
    --------
    >>> escape_qualname("np.int8")
    'np_int8'
    >>> escape_qualname("array-like")
    'array_like'
    >>> escape_qualname("# comment (with braces)")
    '_comment_with_braces_'
    """
    qualname = re.sub(r"\W+|^(?=\d)", "_", name)
    return qualname


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class ContextFormatter:
    """Format messages in context of a location in a file.

    Attributes
    ----------
    path :
        Path to a file for the current context.
    line :
        The line in the given file.
    column :
        The column in the given line.

    Examples
    --------
    >>> from pathlib import Path
    >>> ctx = ContextFormatter(path=Path("file/with/problems.py"))
    >>> ctx.format_message("Message")
    'file/with/problems.py: Message'
    >>> ctx.with_line(3).format_message("Message with line info")
    'file/with/problems.py:3: Message with line info'
    >>> ctx.with_line(3).with_column(2).format_message("Message with column info")
    'file/with/problems.py:3:2: Message with column info'
    """

    path: Path = None
    line: int = None
    column: int = None

    def with_line(self, line=None, *, offset=0):
        """Return a new copy with a modified line.

        Parameters
        ----------
        line : int, optional
            The new line.
        offset : int, optional
            An offset added to the existing line, or the new one if `line` is provided.

        Returns
        -------
        formatter : ContextFormatter
        """
        kwargs = dataclasses.asdict(self)
        if line is None:
            line = kwargs["line"]
        if line is None:
            raise ValueError("can't add offset if the line isn't known")
        kwargs["line"] = line + offset
        new = type(self)(**kwargs)
        return new

    def with_column(self, column=None, *, offset=0):
        """Return a new copy with a modified column.

        Parameters
        ----------
        column : int, optional
            The new column.
        offset : int, optional
            An offset added to the existing column, or the new one if `column` is
            provided.

        Returns
        -------
        formatter : ContextFormatter
        """
        kwargs = dataclasses.asdict(self)
        if column is None:
            column = kwargs["column"]
        if column is None:
            raise ValueError("can't add offset if the column isn't known")
        kwargs["column"] = column + offset
        new = type(self)(**kwargs)
        return new

    def format_message(self, short, *, details=None, ansi_styles=False):
        """Format a message in context of the saved location.

        Parameters
        ----------
        short : str
            A short summarizing message that shouldn't wrap over multiple lines.
        details : str, optional
            An optional multiline message with more details.
        ansi_styles : bool, optional
            Whether to format the output with ANSI escape codes.

        Returns
        -------
        message : str
        """

        def style(x, **kwargs):
            return x

        if ansi_styles:
            style = click.style

        message = short
        if self.path:
            location = style(self.path, bold=True)
            if self.line:
                location = f"{location}:{self.line}"
                if self.column:
                    location = f"{location}:{self.column}"
            message = f"{location}: {message}"

        if details:
            indented = indent(details, prefix="    ", predicate=lambda x: True)
            message = f"{message}\n{indented}"
        return message

    def print_message(self, short, *, details=None):
        """Print a message in context of the saved location.

        Parameters
        ----------
        short : str
            A short summarizing message that shouldn't wrap over multiple lines.
        details : str, optional
            An optional multiline message with more details.
        """
        msg = self.format_message(short, details=details, ansi_styles=True)
        click.echo(msg)
