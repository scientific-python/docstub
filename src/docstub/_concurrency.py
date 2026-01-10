"""Tools for parallel processing."""

import logging
import logging.handlers
import math
import multiprocessing
import os
from collections.abc import Callable, Iterator
from concurrent.futures import Executor
from dataclasses import dataclass

from ._vendored.stdlib import ProcessPoolExecutor

logger: logging.Logger = logging.getLogger(__name__)


class MockPoolExecutor(Executor):
    """Mock executor that does not spawn a thread, interpreter, or process.

    Only implements the used part of the API defined by
    :class:`concurrent.futures.Executor`.
    """

    def map[T](self, fn: Callable[..., T], *iterables, **__) -> Iterator[T]:
        """Returns an iterator equivalent to map(fn, iter).

        Same behavior as :ref:`concurrent.futures.Executor.map` though any
        parameters besides `fn` and `iterables` are ignored.

        Parameters
        ----------
        *iterables : Any
        **__ : Any
        """
        return map(fn, *iterables)


@dataclass(kw_only=True)
class LoggingProcessExecutor:
    """Wrapper around `ProcessPoolExecutor` that forwards logging from workers.

    Parameters
    ----------
    max_workers, initializer, initargs:
        Refer to the documentation :class:`concurrent.futures.ProcessPoolExecutor`.
    logging_handlers:
        Handlers, to which logging records of the worker processes will be
        forwarded too. Worker processes will use the minimal log level of
        the given workers.

    Examples
    --------
    >>> with LoggingProcessExecutor() as pool:  # doctest: +SKIP
    ...     # use `pool.submit` or `pool.map` ...
    """

    max_workers: int | None = None
    logging_handlers: tuple[logging.Handler, ...] = ()
    initializer: Callable | None = None
    initargs: tuple | None = ()

    @staticmethod
    def _initialize_worker(queue, worker_log_level, initializer, initargs):
        """Initialize logging in workers.

        Parameters
        ----------
        queue : multiprocessing.Queue
        worker_log_level : int
        initializer : Callable
        initargs : tuple of Any
        """
        queue_handler = logging.handlers.QueueHandler(queue)
        queue_handler.setLevel(worker_log_level)

        # Could buffering with MemoryHandler improve performance here?
        # memory_handler = logging.handlers.MemoryHandler(
        #     capacity=100, flushLevel=logging.CRITICAL, target=queue_handler
        # )

        root_logger = logging.getLogger()
        root_logger.addHandler(queue_handler)
        root_logger.setLevel(worker_log_level)
        if initializer:
            initializer(*initargs)
        logger.debug("Initialized worker")

    def __enter__(self) -> ProcessPoolExecutor | MockPoolExecutor:
        if self.max_workers == 1:
            logger.debug("Not using concurrency (workers=%i)", self.max_workers)
            return MockPoolExecutor()

        # This sets the logging level of worker processes. Use the minimal level
        # of all handlers here, so that appropriate records are passed on
        worker_log_level = min(*[h.level for h in self.logging_handlers])

        # Sets method by which the worker processes are created, anything besides
        # "spawn" is apparently "broken" on Windows & macOS
        mp_context = multiprocessing.get_context("spawn")

        # A queue, used to pass logging records from worker processes to the
        # current and main one. Naive testing suggests that
        # `multiprocessing.Queue` is faster than `multiprocessing.Manager.Queue`
        self._queue = mp_context.Queue()

        # The actual pool manager that is wrapped here and returned by this
        # context manager
        self._pool = ProcessPoolExecutor(
            max_workers=self.max_workers,
            mp_context=mp_context,
            initializer=self._initialize_worker,
            initargs=(
                self._queue,
                worker_log_level,
                self.initializer,
                self.initargs,
            ),
        )

        # Forwards logging records from the queue to the given logging handlers
        self._listener = logging.handlers.QueueListener(
            self._queue, *self.logging_handlers, respect_handler_level=True
        )
        logger.debug("Starting queue listener")
        self._listener.start()

        return self._pool.__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Parameters
        ----------
        exc_type : type[BaseException] or None
        exc_val : BaseException or None
        exc_tb : TracebackType

        Returns
        -------
        suppress_exception : bool
        """
        if self.max_workers == 1:
            return False

        if exc_type and issubclass(exc_type, KeyboardInterrupt):
            # We want to exit immediately when user interrupts, even if we lose
            # log records that way.
            logger.debug("Terminating workers")
            self._pool.terminate_workers()

            # Ensure that the queue doesn't block (not sure if necessary)
            logger.debug("Calling `cancel_join_thread` on queue")
            self._queue.cancel_join_thread()

        else:
            # We want to wait for any log record to reach the listener
            logger.debug("Shutting down pool")
            self._pool.shutdown(wait=True, cancel_futures=True)

            logger.debug("Stopping queue listener")
            self._listener.stop()

            if not self._queue.empty():
                logger.error("Expected logging queue to be empty, it is not!")

            logger.debug("Closing queue and joining its thread")
            self._queue.close()
            self._queue.join_thread()

        self._queue = None
        self._pool = None
        self._listener = None

        logger.debug("Exiting executor pool")
        return False


def guess_concurrency_params(*, task_count, desired_worker_count=None):
    """Estimate how tasks should be distributed to how many workers.

    Parameters
    ----------
    task_count : int
        The number of task that need to be processed.
    desired_worker_count : int, optional
        If not set, the number of workers is estimated. Set this explicitly
        to force a number of workers. Passing `-1` will also trigger estimation.

    Returns
    -------
    worker_count : int
        The number of workers that should be used.
    chunk_size : int
        The chunk size that should be used to split the tasks among the workers.

    Examples
    --------
    >>> worker_count, chunk_size = guess_concurrency_params(
    ...     task_count=9, desired_worker_count=None
    ... )
    >>> (worker_count, chunk_size)
    (1, 9)
    """
    worker_count = desired_worker_count

    # `process_cpu_count` was added in Python 3.13 onwards
    cpu_count = getattr(os, "process_cpu_count", os.cpu_count)()

    if worker_count is None or worker_count == -1:
        # These crude heuristics were only ever "measured" on one computer
        worker_count = cpu_count
        # Clip to `worker_count <= task_count // 3`
        worker_count = min(worker_count, task_count // 3)
        # For a low number of files it may not be worth spinning up any workers
        if task_count < 10:
            worker_count = 1

    # Clip to [1, cpu_count]
    worker_count = max(1, min(cpu_count, worker_count))

    # Chunking prevents unnecessary pickling of objects that are shared between
    # each task more than once. When `worker_count * chunk_size` is slightly
    # larger than `task_count`, each worker process only ever receives one chunk
    chunk_size = task_count / worker_count
    chunk_size = math.ceil(chunk_size)

    assert isinstance(worker_count, int)
    assert isinstance(chunk_size, int)
    return worker_count, chunk_size
