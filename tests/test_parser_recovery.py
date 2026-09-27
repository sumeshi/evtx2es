import threading
from pathlib import Path

import pytest

from evtx2es.models import Evtx2es as evtx_model


def test_generate_chunks_recovers_after_transient_parser_errors(
    caplog, capsys
):
    class RecoveringIterator:
        def __init__(self):
            self.calls = 0

        def __iter__(self):
            return self

        def __next__(self):
            self.calls += 1
            if self.calls in (2, 3):
                raise RuntimeError("damaged record")
            if self.calls == 1:
                return "first"
            if self.calls == 4:
                return "later valid record"
            raise StopIteration

    assert list(evtx_model.generate_chunks(10, RecoveringIterator())) == [
        ["first", "later valid record"]
    ]
    assert len(caplog.records) == 1
    assert "Skipped 2 EVTX parser error(s)" in caplog.records[0].message
    assert capsys.readouterr().out == ""


def test_generate_chunks_stops_after_repeated_parser_errors():
    class BrokenIterator:
        def __iter__(self):
            return self

        def __next__(self):
            raise RuntimeError("broken parser")

    with pytest.raises(RuntimeError, match="100 consecutive errors") as exc:
        list(evtx_model.generate_chunks(10, BrokenIterator()))
    assert isinstance(exc.value.__cause__, RuntimeError)


def test_multiprocessing_reads_parser_on_calling_thread_and_preserves_order(
    monkeypatch,
):
    caller_thread = threading.get_ident()

    class ThreadBoundIterator:
        def __init__(self):
            self.values = iter(range(5))

        def __iter__(self):
            return self

        def __next__(self):
            assert threading.get_ident() == caller_thread
            return next(self.values)

    class ImmediateResult:
        def __init__(self, pool, function, args):
            self.pool = pool
            self.function = function
            self.args = args

        def get(self):
            try:
                return self.function(*self.args)
            finally:
                self.pool.outstanding -= 1

    class Pool:
        def __init__(self):
            self.outstanding = 0
            self.max_outstanding = 0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def apply_async(self, function, args):
            self.outstanding += 1
            self.max_outstanding = max(self.max_outstanding, self.outstanding)
            return ImmediateResult(self, function, args)

    pool = Pool()

    class Context:
        def Pool(self, _workers):
            return pool

    monkeypatch.setattr(
        evtx_model.Evtx2es,
        "get_multiprocessing_context",
        lambda self: Context(),
    )
    monkeypatch.setattr(evtx_model.Evtx2es, "get_cpu_count", lambda self: 2)

    def fake_process_by_chunk(records, *args):
        return records

    monkeypatch.setattr(evtx_model, "process_by_chunk", fake_process_by_chunk)

    evtx = evtx_model.Evtx2es.__new__(evtx_model.Evtx2es)
    evtx.path = Path("dummy.evtx")
    evtx.parser = type(
        "Parser", (), {"records_json": lambda _self: ThreadBoundIterator()}
    )()

    assert list(evtx.gen_records("0", True, 2)) == [[0, 1], [2, 3], [4]]
    assert 2 <= pool.max_outstanding <= 4
