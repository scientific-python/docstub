# File generated with docstub

import logging
import logging.handlers
import math
import multiprocessing
import os
from collections.abc import Callable, Iterator
from concurrent.futures import Executor
from dataclasses import dataclass
from types import TracebackType
from typing import Any

from ._vendored.stdlib import ProcessPoolExecutor

logger: logging.Logger

class MockPoolExecutor(Executor):
    def map[T](
        self, fn: Callable[..., T], *iterables: Any, **__: Any
    ) -> Iterator[T]: ...

@dataclass(kw_only=True)
class LoggingProcessExecutor:

    max_workers: int | None = ...
    logging_handlers: tuple[logging.Handler, ...] = ...
    initializer: Callable | None = ...
    initargs: tuple | None = ...

    @staticmethod
    def _initialize_worker(
        queue: multiprocessing.Queue,
        worker_log_level: int,
        initializer: Callable,
        initargs: tuple[Any],
    ) -> None: ...
    def __enter__(self) -> ProcessPoolExecutor | MockPoolExecutor: ...
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType,
    ) -> bool: ...

def guess_concurrency_params(
    *, task_count: int, desired_worker_count: int | None = ...
) -> tuple[int, int]: ...
