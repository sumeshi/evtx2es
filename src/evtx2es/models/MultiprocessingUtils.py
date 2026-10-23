"""Process setup and bounded, ordered task submission shared by the tools."""

from collections import deque
import multiprocessing as mp
import os
import sys


class SafeMultiprocessingMixin:
    """Choose the process context and CPU fallback consistently."""

    @staticmethod
    def get_multiprocessing_context() -> mp.context.BaseContext:
        if sys.version_info >= (3, 13) or "pytest" in sys.modules:
            try:
                return mp.get_context("spawn")
            except RuntimeError:
                return mp.get_context()
        return mp.get_context()

    @staticmethod
    def get_cpu_count() -> int:
        try:
            return mp.cpu_count()
        except NotImplementedError:
            return os.cpu_count() or 1


def ordered_pool_results(pool, process, items, max_pending):
    """Consume inputs on the caller thread and yield at most bounded FIFO work.

    The caller owns the pool and its lifetime. Only materialized items are sent
    to workers; native iterators stay on the thread that advances this iterator.
    """
    if type(max_pending) is not int or max_pending <= 0:
        raise ValueError("max_pending must be a positive integer")
    pending = deque()
    for item in items:
        pending.append(pool.apply_async(process, (item,)))
        if len(pending) >= max_pending:
            yield pending.popleft().get()
    while pending:
        yield pending.popleft().get()
