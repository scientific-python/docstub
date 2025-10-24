# File generated with docstub

import logging
from collections.abc import Callable
from functools import cached_property
from pathlib import Path
from typing import Any, Protocol

logger: logging.Logger

CACHE_DIR_NAME: str

CACHEDIR_TAG_CONTENT: str

GITHUB_IGNORE_CONTENT: str

def _directory_size(path: Path) -> int: ...
def create_cache(path: Path) -> None: ...
def validate_cache(path: Path) -> None: ...

class FuncSerializer[T](Protocol):

    suffix: str

    def hash_args(self, *args: Any, **kwargs: Any) -> str: ...
    def serialize(self, data: T) -> bytes: ...
    def deserialize(self, raw: bytes) -> T: ...

class FileCache:
    func: Callable
    serializer: FuncSerializer
    sub_dir: str
    cache_hits: int
    cache_misses: int
    cached_last_call: bool | None

    def __init__(
        self,
        *,
        func: Callable,
        serializer: FuncSerializer,
        cache_dir: Path,
        sub_dir: str | None = ...,
    ) -> None: ...
    @cached_property
    def cache_dir(self) -> Path: ...
    @property
    def cache_sub_dir(self) -> None: ...
    def __call__(self, *args: Any, **kwargs: Any) -> Any: ...
