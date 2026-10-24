# coding: utf-8
import orjson
import importlib
from pathlib import Path

import pytest
import evtx2es as evtx2es_package
from evtx2es.views.Evtx2esView import entry_point as e2e
from evtx2es.views.Evtx2jsonView import entry_point as e2j

# utils
def get_json_records(path: Path) -> list:
    data = path.read_bytes()
    if path.suffix == ".jsonl":
        return [orjson.loads(line) for line in data.splitlines()]
    return orjson.loads(data)


def assert_native_status_is_preserved(records):
    by_id = {record["winlog"]["record_id"]: record for record in records}
    for record_id, status in ((246692, "0x20"), (227432, "0xc000013a")):
        winlog = by_id[record_id]["winlog"]
        assert winlog["event_data"]["Status"] == status
        assert "Status" not in winlog.get("event_data_original", {})


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
@pytest.mark.usefixtures("prepare_eventlog")
@pytest.mark.parametrize("output_format", ["json", "jsonl"])
def test__evtx2json_convert(monkeypatch, output_format):
    path = f"tests/cache/Security.{output_format}"
    argv = [
        "evtx2json", "--format", output_format, "-o", path,
        "tests/cache/Security.evtx",
    ]
    with monkeypatch.context() as m:
        m.setattr("sys.argv", argv)
        e2j()
    records = get_json_records(Path(path))
    assert len(records) == 62031
    assert_native_status_is_preserved(records)

@pytest.mark.usefixtures("prepare_eventlog")
@pytest.mark.parametrize("output_format", ["json", "jsonl"])
def test__evtx2json_convert_multiprocessing(monkeypatch, output_format):
    path = f"tests/cache/Security-m.{output_format}"
    argv = [
        "evtx2json", "--format", output_format, "-o", path, "-m",
        "tests/cache/Security.evtx",
    ]
    with monkeypatch.context() as m:
        m.setattr("sys.argv", argv)
        e2j()
    records = get_json_records(Path(path))
    assert len(records) == 62031
    assert_native_status_is_preserved(records)


@pytest.mark.usefixtures("prepare_eventlog")
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
    assert_native_status_is_preserved(records)
    assert_native_status_is_preserved(multiprocessing_records)


def test__gen_records_yields_each_chunk_without_extra_buffering(monkeypatch):
    evtx2es_model = importlib.import_module("evtx2es.models.Evtx2es")

    class DummyParser:
        def records_json(self):
            return iter(range(5))

    def fake_process_by_chunk(records, filepath, shift, additional_tags=None, on_record_error=None):
        return list(records)

    monkeypatch.setattr(evtx2es_model, "process_by_chunk", fake_process_by_chunk)

    evtx = evtx2es_model.Evtx2es.__new__(evtx2es_model.Evtx2es)
    evtx.path = Path("dummy.evtx")
    evtx.parser = DummyParser()

    assert list(evtx.gen_records(None, False, 2)) == [[0, 1], [2, 3], [4]]


def test__evtx2json_public_api_closes_evtx(monkeypatch):
    class DummyEvtx:
        closed = False

        def __init__(self, input_path):
            self.input_path = input_path
            self.diagnostics = []

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
