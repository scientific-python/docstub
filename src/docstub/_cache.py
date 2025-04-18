import logging
from functools import cached_property
from typing import Protocol

logger = logging.getLogger(__name__)


CACHEDIR_TAG_CONTENT = """\
Signature: 8a477f597d28d172789f06886806bc55\
# This file is a cache directory tag automatically created by docstub.\n"
# For information about cache directory tags see https://bford.info/cachedir/\n"
"""


def _directory_size(path):
    """Estimate total size of a directory's content in bytes.

    Parameters
    ----------
    path : Path

    Returns
    -------
    total_bytes : int
        Total size of all objects in bytes.
    """
    if not path.is_dir():
        msg = f"{path} doesn't exist, can't determine size"
        raise FileNotFoundError(msg)
    files = path.rglob("*")
    total_bytes = sum(f.stat().st_size for f in files)
    return total_bytes


def create_cache(path):
    """Create a cache directory.

    Parameters
    ----------
    path : Path
        Directory of the cache. The directory and it's parents will be created if it
        doesn't exist yet.
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
        "# This file is a cache directory automatically created by docstub.\n" "*\n"
    )
    if not gitignore_path.is_file():
        with open(gitignore_path, "w") as fp:
            fp.write(gitignore_content)


class FuncSerializer[T](Protocol):
    """Defines an interface to serialize and deserialize results of a function.

    This interface is used by `FileCache` to cache results of a

    Attributes
    ----------
    suffix :
        A suffix corresponding to the format of the serialized data, e.g. ".json".
    """

    suffix: str

    def hash_args(self, *args, **kwargs) -> str:
        """Compute a unique hash from the arguments passed to a function."""

    def serialize(self, data: T) -> bytes:
        """Serialize results of a function from `T` to bytes."""

    def deserialize(self, raw: bytes) -> T:
        """Deserialize results of a function from bytes back to `T`."""


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
        """Path to the named subdirectory inside the cache.

        Warns when cache size exceeds 512 MiB.
        """
        cache_dir = self._cache_dir
        create_cache(cache_dir)
        if _directory_size(cache_dir) > 512 * 1024**2:
            logger.warning("cache size at %r exceeds 512 MiB", cache_dir)
        _named_cache_dir = cache_dir / self.name
        _named_cache_dir.mkdir(parents=True, exist_ok=True)
        return _named_cache_dir

    def __call__(self, *args, **kwargs):
        """Call the wrapped `func` and cache each result in a file."""
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
