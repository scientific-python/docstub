import dataclasses
import itertools
import re
from functools import lru_cache
from pathlib import Path
from textwrap import indent
from zlib import crc32

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


@lru_cache(maxsize=100)
def module_name_from_path(path):
    """Find the full name of a module within its package from its file path.

    Parameters
    ----------
    path : Path

    Returns
    -------
    name : str

    Examples
    --------
    >>> from pathlib import Path
    >>> module_name_from_path(Path(__file__))
    'docstub._utils'
    >>> import docstub
    >>> module_name_from_path(Path(docstub.__file__))
    'docstub'
    """
    if not path.is_file():
        raise FileNotFoundError(f"`path` is not an existing file: {path!r}")

    name_parts = []
    if path.name != "__init__.py":
        name_parts.insert(0, path.stem)

    directory = path.parent
    while True:
        is_in_package = (directory / "__init__.py").is_file()
        if is_in_package:
            name_parts.insert(0, directory.name)
            directory = directory.parent
        else:
            break

    name = ".".join(name_parts)
    return name


def pyfile_checksum(path):
    """Compute a unique key for a Python file.

    The key takes into account the given `path`, the relative position if the
    file is part of a Python package and the file's content.

    Parameters
    ----------
    path : Path

    Returns
    -------
    key : str
    """
    module_name = module_name_from_path(path).encode()
    absolute_path = str(path.resolve()).encode()
    with open(path, "rb") as fp:
        content = fp.read()
    key = crc32(content + module_name + absolute_path)
    return key


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class ErrorReporter:
    """Format error messages in context of a location in a file.

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
    >>> rep = ErrorReporter()
    >>> rep.message("Message")
    Message
    <BLANKLINE>
    >>> rep = rep.copy_with(path=Path("file/with/problems.py"))
    >>> rep.copy_with(line=3).message("Message with line info")
    file...problems.py:3: Message with line info
    <BLANKLINE>
    >>> rep.copy_with(line=4, column=2).message("With line & column info")
    file...problems.py:4:2: With line & column info
    <BLANKLINE>
    >>> rep.message("Summary", details="More details")
    file...problems.py: Summary
        More details
    <BLANKLINE>
    """

    path: Path | None = None
    line: int | None = None
    column: int | None = None

    def copy_with(self, *, path=None, line=None, column=None, line_offset=None):
        """Return a new copy with the modified attributes.

        Parameters
        ----------
        path : Path, optional
        line : int, optional
        column : int, optional
        line_offset : int, optional

        Returns
        -------
        new : Self
        """
        kwargs = dataclasses.asdict(self)
        if path:
            kwargs["path"] = path
        if line:
            kwargs["line"] = line
        if line_offset:
            kwargs["line"] += line_offset
        if column:
            kwargs["column"] = column
        new = type(self)(**kwargs)
        return new

    def message(self, short, *, details=None):
        """Print a message in context of the saved location.

        Parameters
        ----------
        short : str
            A short summarizing message that shouldn't wrap over multiple lines.
        details : str, optional
            An optional multiline message with more details.
        """
        message = click.style(short, bold=True)
        location = self.format_location(
            path=self.path, line=self.line, column=self.column
        )
        if location:
            message = f"{location}: {message}"

        if details:
            indented = indent(details, prefix="    ")
            message = f"{message}\n{indented}"

        message = f"{message.strip()}\n"
        click.echo(message)

    def __post_init__(self):
        if self.path is not None and not isinstance(self.path, Path):
            msg = f"expected `path` to be of type `Path`, got {type(self.path)!r}"
            raise TypeError(msg)

    @staticmethod
    def format_location(*, path, line, column):
        location = ""
        if path:
            location = path
            if line:
                location = f"{location}:{line}"
                if column:
                    location = f"{location}:{column}"
        if location:
            location = click.style(location, fg="magenta")
        return location

    @staticmethod
    def underline(line):
        underlined = f"{line}\n" f"{click.style('^' * len(line), fg='red', bold=True)}"
        return underlined


@dataclasses.dataclass(kw_only=True, frozen=True)
class GroupedErrorReporter(ErrorReporter):
    """Format & group error messages in context of a location in a file.

    Examples
    --------
    >>> from pathlib import Path
    >>> rep = GroupedErrorReporter()
    >>> rep.message("Syntax error")
    >>> rep = rep.copy_with(path=Path("file/with/problems.py"))
    >>> rep.copy_with(line=3).message("Syntax error")
    >>> rep.copy_with(line=4, column=2).message("Unknown doctype")
    >>> rep.message("Unknown doctype")
    >>> rep.print_grouped()
    Syntax error (x2)
        <unknown location>
        ...problems.py:3
    <BLANKLINE>
    Unknown doctype (x2)
        ...problems.py
        ...problems.py:4:2
    <BLANKLINE>
    """

    _messages: list = dataclasses.field(default_factory=list)

    def copy_with(self, *, path=None, line=None, column=None, line_offset=None):
        """Return a new copy with the modified attributes.

        Parameters
        ----------
        path : Path, optional
        line : int, optional
        column : int, optional
        line_offset : int, optional

        Returns
        -------
        new : Self
        """
        new = super().copy_with(
            path=path, line=line, column=column, line_offset=line_offset
        )
        # Explicitly override `_message` since super method relies on
        # `dataclasses.asdict` which performs deep copies on lists, while
        #  we want to collect all messages in one list
        object.__setattr__(new, "_messages", self._messages)
        return new

    def message(self, short, *, details=None):
        """Print a message in context of the saved location.

        Parameters
        ----------
        short : str
            A short summarizing message that shouldn't wrap over multiple lines.
        details : str, optional
            An optional multiline message with more details.
        """
        self._messages.append(
            {
                "short": short.strip(),
                "details": details.strip() if details else details,
                "path": self.path,
                "line": self.line,
                "column": self.column,
            }
        )

    def print_grouped(self):
        """Print all collected messages in groups."""

        def key(message):
            return (
                message["short"] or "",
                message["details"] or "",
                message["path"] or Path(),
                message["line"] or -1,
                message["column"] or -1,
            )

        groups = {}
        for message in sorted(self._messages, key=key):
            group_name = (message["short"], message["details"])
            if group_name not in groups:
                groups[group_name] = []
            groups[group_name].append(message)

        # Show largest groups last
        groups_by_size = sorted(groups.items(), key=lambda x: len(x[1]))

        for (short, details), group in groups_by_size:
            formatted = click.style(short, bold=True)
            if len(group) > 1:
                formatted = f"{formatted} (x{len(group)})"
            if details:
                indented = indent(details, prefix="    ")
                formatted = f"{formatted}\n{indented}"

            occurrences = []
            for message in group:
                location = (
                    self.format_location(
                        path=message["path"],
                        line=message["line"],
                        column=message["column"],
                    )
                    or "<unknown location>"
                )
                occurrences.append(location)
            occurrences = "\n".join(occurrences)
            occurrences = indent(occurrences, prefix="    ")
            formatted = f"{formatted}\n{occurrences}\n"

            click.echo(formatted)


class DocstubError(Exception):
    """An error raised by docstub."""
