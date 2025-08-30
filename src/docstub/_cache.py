import logging
from functools import cached_property
from typing import Any, Protocol

logger: logging.Logger = logging.getLogger(__name__)


CACHE_DIR_NAME: str = ".docstub_cache"


CACHEDIR_TAG_CONTENT: str = """\
Signature: 8a477f597d28d172789f06886806bc55
# Mark this directory as a cache [1], created by docstub [2]
# [1] https://bford.info/cachedir/
# [2] https://github.com/scientific-python/docstub
"""


GITHUB_IGNORE_CONTENT: str = """\
# Make git ignore this cache directory, created by docstub [1]
# [1] https://github.com/scientific-python/docstub
*
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

    if not cachdir_tag_path.is_file():
        with open(cachdir_tag_path, "w") as fp:
            fp.write(CACHEDIR_TAG_CONTENT)

    gitignore_path = path / ".gitignore"
    if not gitignore_path.is_file():
        with open(gitignore_path, "w") as fp:
            fp.write(GITHUB_IGNORE_CONTENT)


def validate_cache(path):
    """Make sure the given path is a cache created by docstub.

    Parameters
    ----------
    path : Path

    Raises
    ------
    FileNotFoundError
    """
    if not path.is_dir():
        raise FileNotFoundError(f"expected '{path}' to be a valid directory")

    if not path.name == CACHE_DIR_NAME:
        raise FileNotFoundError(
            f"expected directory '{path}' be named '{CACHE_DIR_NAME}'"
        )

    cachdir_tag_path = path / "CACHEDIR.TAG"
    if not cachdir_tag_path.is_file():
        raise FileNotFoundError(f"expected '{path}' to contain a 'CACHEDIR.TAG' file")
    gitignore_path = path / ".gitignore"
    if not gitignore_path.is_file():
        raise FileNotFoundError(f"expected '{path}' to contain a '.gitignore' file")


class FuncSerializer[T](Protocol):
    """Defines an interface to serialize and deserialize results of a function.

    This interface is used by `FileCache` to cache results of a

    Attributes
    ----------
    suffix :
        A suffix corresponding to the format of the serialized data, e.g. ".json".
    """

    suffix: str

    def hash_args(self, *args: Any, **kwargs: Any) -> str:
        """Compute a unique hash from the arguments passed to a function."""

    def serialize(self, data: T) -> bytes:
        """Serialize results of a function from `T` to bytes."""

    def deserialize(self, raw: bytes) -> T:
        """Deserialize results of a function from bytes back to `T`."""


class FileCache:
    """Cache results from a function call as a file on disk.

    This class can cache results of a function to the disk. A unique key is
    generated from the arguments to the function, and the result is cached
    inside a file named after this key.

    Attributes
    ----------
    func : Callable
        The function whose output shall be cached.
    serializer : FuncSerializer
        An interface that matches the given `func`. It must implement the
        `FuncSerializer` protocol.
    sub_dir : str
        A unique name to structure multiple / parallel caches inside `cache_dir`.
    cache_hits, cache_misses : int
        Records how many times this object returned results from a cache (hits)
        or by computing it (misses).
    cached_last_call : bool or None
        Whether the last call was cached. ``None`` if not called yet.
    """

    def __init__(self, *, func, serializer, cache_dir, sub_dir=None):
        """
        Parameters
        ----------
        func : Callable
            The function whose output shall be cached.
        serializer : FuncSerializer
            An interface that matches the given `func`. It must implement the
            `FuncSerializer` protocol.
        cache_dir : Path
            The directory of the cache.
        sub_dir : str
            A unique name to structure multiple / parallel caches inside `cache_dir`.
        """
        self.func = func
        self.serializer = serializer
        self._cache_dir = cache_dir
        self.sub_dir = sub_dir

        self.cache_hits = 0
        self.cache_misses = 0
        self.cached_last_call = None

    @cached_property
    def cache_dir(self):
        """Return and create cache dir on first use - also check its size.

        Returns
        -------
        cache_dir : Path
        """
        create_cache(self._cache_dir)

        if _directory_size(self._cache_dir) > 512 * 1024**2:
            logger.warning("Cache size at %r exceeds 512 MiB", self._cache_dir)

        return self._cache_dir

    @property
    def cache_sub_dir(self):
        """Create and return path to a specific subdirectory inside the cache.

        Warns when cache size exceeds 512 MiB.
        """
        named_dir = self.cache_dir
        if self.sub_dir:
            named_dir /= self.sub_dir
        named_dir.mkdir(parents=True, exist_ok=True)

        return named_dir

    def __call__(self, *args, **kwargs):
        """Call the wrapped `func` and cache each result in a file.

        Parameters
        ----------
        args : Any
        kwargs : Any

        Returns
        -------
        data : Any
        """
        key = self.serializer.hash_args(*args, **kwargs)
        entry_path = self.cache_sub_dir / f"{key}{self.serializer.suffix}"

        if entry_path.is_file():
            # `data` is already cached
            with entry_path.open("rb") as fp:
                raw = fp.read()
            data = self.serializer.deserialize(raw)

            self.cached_last_call = True
            self.cache_hits += 1

        else:
            # `data` isn't cached, write cache
            data = self.func(*args, **kwargs)
            raw = self.serializer.serialize(data)
            with entry_path.open("xb") as fp:
                fp.write(raw)

            self.cached_last_call = False
            self.cache_misses += 1

        return data
