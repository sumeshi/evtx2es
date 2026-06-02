# coding: utf-8
import orjson
import importlib
from pathlib import Path

import pytest
import evtx2es as evtx2es_package
from evtx2es.views.Evtx2esView import entry_point as e2e
from evtx2es.views.Evtx2jsonView import entry_point as e2j

# utils
def get_json_length(path: Path) -> int:
    if path.is_dir():
        return 0
    return len(orjson.loads(path.read_bytes()))


# command-line test cases
def test__evtx2es_help(monkeypatch):
    argv = ["evtx2es", "-h"]
    with pytest.raises(SystemExit) as exited:
        with monkeypatch.context() as m:
            m.setattr("sys.argv", argv)
            e2e()
        assert exited.value.code == 0

def test__evtx2es_version(monkeypatch):
    argv = ["evtx2es", "-v"]
    with pytest.raises(SystemExit) as exited:
        with monkeypatch.context() as m:
            m.setattr("sys.argv", argv)
            e2e()
        assert exited.value.code == 0

def test__evtx2json_help(monkeypatch):
    argv = ["evtx2json", "-h"]
    with pytest.raises(SystemExit) as exited:
        with monkeypatch.context() as m:
            m.setattr("sys.argv", argv)
            e2j()
        assert exited.value.code == 0

def test__evtx2json_version(monkeypatch):
    argv = ["evtx2json", "-v"]
    with pytest.raises(SystemExit) as exited:
        with monkeypatch.context() as m:
            m.setattr("sys.argv", argv)
            e2j()
        assert exited.value.code == 0


# behavior test cases 
def test__evtx2json_convert(monkeypatch):
    path = 'tests/cache/Security.json'
    argv = ["evtx2json", "-o", path, "tests/cache/Security.evtx"]
    with monkeypatch.context() as m:
        m.setattr("sys.argv", argv)
        e2j()
    assert get_json_length(Path(path)) == 62031

def test__evtx2json_convert_multiprocessing(monkeypatch):
    path = 'tests/cache/Security-m.json'
    argv = ["evtx2json", "-o", path, "-m", "tests/cache/Security.evtx"]
    with monkeypatch.context() as m:
        m.setattr("sys.argv", argv)
        e2j()
    assert get_json_length(Path(path)) == 62031


def test__evtx2json_multiprocessing_keeps_record_order():
    records = evtx2es_package.evtx2json(
        "tests/cache/Security.evtx", multiprocess=False
    )
    multiprocessing_records = evtx2es_package.evtx2json(
        "tests/cache/Security.evtx", multiprocess=True
    )

    record_ids = [record["winlog"]["record_id"] for record in records]
    multiprocessing_record_ids = [
        record["winlog"]["record_id"] for record in multiprocessing_records
    ]

    assert multiprocessing_record_ids == record_ids


def test__gen_records_yields_each_chunk_without_extra_buffering(monkeypatch):
    evtx2es_model = importlib.import_module("evtx2es.models.Evtx2es")

    class DummyParser:
        def records_json(self):
            return iter(range(5))

    def fake_process_by_chunk(records, filepath, shift, additional_tags=None):
        return list(records)

    monkeypatch.setattr(evtx2es_model, "process_by_chunk", fake_process_by_chunk)

    evtx = evtx2es_model.Evtx2es.__new__(evtx2es_model.Evtx2es)
    evtx.path = Path("dummy.evtx")
    evtx.parser = DummyParser()

    assert list(evtx.gen_records("0", False, 2)) == [[0, 1], [2, 3], [4]]


def test__evtx2json_public_api_closes_evtx(monkeypatch):
    class DummyEvtx:
        closed = False

        def __init__(self, input_path):
            self.input_path = input_path

        def gen_records(self, **kwargs):
            yield []

        def close(self):
            DummyEvtx.closed = True

    monkeypatch.setattr(evtx2es_package, "Evtx2es", DummyEvtx)

    assert evtx2es_package.evtx2json("dummy.evtx") == []
    assert DummyEvtx.closed


def test__evtx2es_public_api_passes_verify_certs(monkeypatch):
    captured = {}

    class DummyPresenter:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def bulk_import(self):
            pass

    monkeypatch.setattr(evtx2es_package, "Evtx2esPresenter", DummyPresenter)

    evtx2es_package.evtx2es("dummy.evtx", verify_certs=False)

    assert captured["verify_certs"] is False
