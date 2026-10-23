"""Shared process contracts: lazy owner-thread input and ordered bounded work."""

import importlib
from multiprocessing.pool import ThreadPool
from pathlib import Path
import threading

import pytest


PACKAGE = next(
    path.name
    for path in (Path(__file__).resolve().parents[1] / "src").iterdir()
    if (path / "models" / "MultiprocessingUtils.py").is_file()
)
shared = importlib.import_module(f"{PACKAGE}.models.MultiprocessingUtils")


def test_ordered_work_consumes_native_style_input_lazily_on_owner_thread():
    owner = threading.get_ident()
    consumed = []
    second_finished = threading.Event()

    def items():
        for value in range(12):
            assert threading.get_ident() == owner
            consumed.append(value)
            yield value

    def process(value):
        assert threading.get_ident() != owner
        if value == 0:
            assert second_finished.wait(timeout=5)
        elif value == 1:
            second_finished.set()
        return value

    with ThreadPool(2) as pool:
        results = shared.ordered_pool_results(pool, process, items(), 4)
        assert consumed == []
        assert next(results) == 0
        assert consumed == [0, 1, 2, 3]
        assert [0, *results] == list(range(12))


def test_unexpected_task_error_is_raised_in_input_order():
    def process(value):
        if value == 1:
            raise RuntimeError("task failed")
        return value

    with ThreadPool(2) as pool:
        results = shared.ordered_pool_results(pool, process, range(6), 4)
        try:
            assert next(results) == 0
            with pytest.raises(RuntimeError, match="task failed"):
                next(results)
        finally:
            results.close()


@pytest.mark.parametrize("max_pending", [0, -1, False, 1.5, None])
def test_invalid_pending_bound_fails_before_inputs_are_consumed(max_pending):
    def items():
        pytest.fail("invalid bound consumed the input")
        yield None

    with pytest.raises(ValueError, match="max_pending"):
        next(shared.ordered_pool_results(None, None, items(), max_pending))
