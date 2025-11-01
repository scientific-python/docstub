# File generated with docstub

import logging
import logging.handlers
import math
import multiprocessing
import os
from collections.abc import Callable, Iterable
from concurrent.futures import Executor
from dataclasses import dataclass
from multiprocessing import Queue
from types import TracebackType
from typing import Any

from ._vendored.stdlib import ProcessPoolExecutor

logger: logging.Logger

class MockPoolExecutor(Executor):
    def map(self, fn: Callable, *iterables: Any, **__: Any) -> Iterable: ...

@dataclass(kw_only=True)
class LoggingProcessExecutor:

    max_workers: int | None = ...
    logging_handlers: tuple[logging.Handler, ...] = ...
    initializer: Callable | None = ...
    initargs: tuple | None = ...

    @staticmethod
    def _initialize_worker(
        queue: Queue, worker_log_level: int, initializer: Callable, initargs: tuple[Any]
    ) -> None: ...
    def __enter__(self) -> ProcessPoolExecutor | MockPoolExecutor: ...
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType,
    ) -> bool: ...

def guess_concurrency_params(
    *, task_count: int, worker_count: int | None = ...
) -> tuple[int, int]: ...
