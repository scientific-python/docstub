import dataclasses
import itertools
import re
from functools import cached_property, lru_cache
from pathlib import Path
from textwrap import indent
from typing import Protocol
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


@lru_cache(maxsize=10)
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


def create_cachedir(path):
    """Create a cache directory

    Parameters
    ----------
    path : Path
    """
    path.mkdir(parents=True, exist_ok=True)
    cachdir_tag_path = path / "CACHEDIR.TAG"
    cachdir_tag_content = (
        "Signature: 8a477f597d28d172789f06886806bc55\n"
        "# This file is a cache directory tag automatically created by docstub.\n"
        "# For information about cache directory tags see https://bford.info/cachedir/\n"
    )
    if not cachdir_tag_path.is_file():
        with open(cachdir_tag_path, "w") as fp:
            fp.write(cachdir_tag_content)

    gitignore_path = path / ".gitignore"
    gitignore_content = (
        "# This file is a cache directory tag automatically created by docstub.\n" "*\n"
    )
    if not gitignore_path.is_file():
        with open(gitignore_path, "w") as fp:
            fp.write(gitignore_content)


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
    'file...problems.py: Message'
    >>> ctx.with_line(3).format_message("Message with line info")
    'file...problems.py:3: Message with line info'
    >>> ctx.with_line(3).with_column(2).print_message("Message with column info")
    file...problems.py:3:2: Message with column info
    >>> ctx.print_message("Summary", details="More details")
    file...problems.py: Summary
        More details
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

    def __post_init__(self):
        if self.path is not None and not isinstance(self.path, Path):
            msg = f"expected `path` to be of type `Path`, got {type(self.path)!r}"
            raise TypeError(msg)


class FuncSerializer[T](Protocol):
    """Defines an interface to serialize and deserialize results of a function."""

    suffix: str

    def hash_args(self, *args, **kwargs) -> str: ...
    def serialize(self, data: T) -> bytes: ...
    def deserialize(self, raw: bytes) -> T: ...


class FileCache:
    """Cache results from a function call as a files on disk.

    This class can cache results of a function to the disk. A unique key is
    generated from the arguments to the function, and the result is cached
    inside a file named after this key.
    """

    def __init__(self, *, func, serializer, cache_dir, name):
        """
        Parameters
        ----------
        func : callable
            The function whose output shall be cached.
        serializer : FuncSerializer
            An interface that matches the given `func`. It must implement the
            `FileCachIO` protocol.
        cache_dir : Path
            The directory of the cache.
        name : str
            A unique name to separate parallel caches inside `cache_dir`.
        """
        self.func = func
        self.serializer = serializer
        self._cache_dir = cache_dir
        self.name = name

    @cached_property
    def named_cache_dir(self):
        cache_dir = self._cache_dir
        create_cachedir(cache_dir)
        _named_cache_dir = cache_dir / self.name
        _named_cache_dir.mkdir(parents=True, exist_ok=True)
        return _named_cache_dir

    def __call__(self, *args, **kwargs):
        key = self.serializer.hash_args(*args, **kwargs)
        entry_path = self.named_cache_dir / f"{key}{self.serializer.suffix}"
        if entry_path.is_file():
            with entry_path.open("rb") as fp:
                raw = fp.read()
            data = self.serializer.deserialize(raw)
        else:
            data = self.func(*args, **kwargs)
            raw = self.serializer.serialize(data)
            with entry_path.open("xb") as fp:
                fp.write(raw)
        return data
