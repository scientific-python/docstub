# File generated with docstub

import os
import re
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor as _ProcessPoolExecutor

def _fnmatch_translate(pat: str, STAR: str, QUESTION_MARK: str) -> str: ...
def glob_translate(
    pat: str,
    *,
    recursive: bool = ...,
    include_hidden: bool = ...,
    seps: Sequence[str] | None = ...,
) -> str: ...

if not hasattr(_ProcessPoolExecutor, "terminate_workers"):
    _TERMINATE: str
    _KILL: str

    _SHUTDOWN_CALLBACK_OPERATION: set[str]

    class ProcessPoolExecutor(_ProcessPoolExecutor):
        def _force_shutdown(self, operation: str) -> None: ...
        def terminate_workers(self) -> None: ...
        def kill_workers(self) -> None: ...

else:
    ProcessPoolExecutor: _ProcessPoolExecutor  # type: ignore[no-redef]
