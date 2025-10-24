# File generated with docstub

import itertools
import re
from collections.abc import Callable
from functools import lru_cache, wraps
from pathlib import Path
from zlib import crc32

def accumulate_qualname(qualname: str, *, start_right: bool = ...) -> None: ...
def escape_qualname(name: str) -> str: ...
def _resolve_path_before_caching(func: Callable) -> Callable: ...
def module_name_from_path(path: Path) -> str: ...
def pyfile_checksum(path: Path) -> str: ...

class DocstubError(Exception):
    pass
