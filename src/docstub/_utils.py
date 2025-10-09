import itertools
import re
from functools import lru_cache
from zlib import crc32


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
            break
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


class DocstubError(Exception):
    """An error raised by docstub."""
