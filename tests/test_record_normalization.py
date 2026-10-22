import json
import sys

import pytest

import evtx2es as api
from evtx2es.models import Evtx2es as model
from evtx2es.presenters.Evtx2jsonPresenter import Evtx2jsonPresenter
from evtx2es.views.Evtx2jsonView import entry_point


def raw_record(record_id):
    return {
        "event_record_id": record_id,
        "data": json.dumps(
            {
                "Event": {
                    "System": {
                        "Provider": {"#attributes": {"Name": "Example"}},
                        "EventID": 1,
                        "TimeCreated": {
                            "#attributes": {"SystemTime": "2025-01-02T03:04:05Z"}
                        },
                        "Channel": "Security",
                        "Computer": "HOST01",
                        "EventRecordID": record_id,
                        "Task": 1,
                    },
                },
            }
        ),
    }


@pytest.mark.parametrize(
    "field, output_field",
    [
        ("Task", "task"),
        ("Channel", "channel"),
        ("EventRecordID", "record_id"),
        ("Computer", "computer_name"),
    ],
)
def test_optional_system_fields_do_not_drop_valid_records(field, output_field):
    record = raw_record(2)
    data = json.loads(record["data"])
    del data["Event"]["System"][field]
    record["data"] = json.dumps(data)
    diagnostics = []

    records = model.process_by_chunk(
        [raw_record(1), record, raw_record(3)],
        "sample.evtx",
        None,
        on_record_error=diagnostics.append,
    )

    assert len(records) == 3
    assert records[1]["winlog"][output_field] is None
    assert not diagnostics
    if field == "Channel":
        assert records[1]["event"]["action"] == "eventlog-1"


def test_optional_time_and_provider_name_do_not_invent_metadata():
    record = raw_record(1)
    data = json.loads(record["data"])
    system = data["Event"]["System"]
    del system["TimeCreated"]
    system["Provider"] = None
    record["data"] = json.dumps(data)

    formatted = model.format_record(record, "sample.evtx", None)

    assert formatted["@timestamp"] is None
    assert formatted["event"]["created"] is None
    assert formatted["event"]["provider"] is None
    assert formatted["winlog"]["provider"] == {"name": None, "guid": None}


def test_valid_json_with_a_failed_field_conversion_keeps_neighboring_records():
    record = raw_record(2)
    data = json.loads(record["data"])
    data["Event"]["EventData"] = {"ProcessId": "0xnot-hex"}
    record["data"] = json.dumps(data)
    diagnostics = []

    records = model.process_by_chunk(
        [raw_record(1), record, raw_record(3)],
        "sample.evtx",
        None,
        on_record_error=diagnostics.append,
    )

    assert [record["winlog"]["record_id"] for record in records] == [1, 3]
    assert len(diagnostics) == 1
    assert diagnostics[0]["record_id"] == 2
    assert diagnostics[0]["stage"] == "normalization"
    assert diagnostics[0]["error"].startswith("ValueError:")


@pytest.mark.parametrize("chunk_size", [1, 500])
@pytest.mark.parametrize("multiprocess", [False, True])
def test_record_normalization_recovers_with_diagnostics_including_spawn_workers(
    tmp_path,
    monkeypatch,
    chunk_size,
    multiprocess,
):
    records = [
        raw_record(1),
        {"event_record_id": 2, "data": "invalid JSON"},
        raw_record(3),
    ]
    evtx = model.Evtx2es.__new__(model.Evtx2es)
    evtx.path = tmp_path / "sample.evtx"
    evtx.parser = type("Parser", (), {"records_json": lambda _self: iter(records)})()
    monkeypatch.setattr(model.Evtx2es, "get_cpu_count", lambda _self: 2)

    batches = list(evtx.gen_records(None, multiprocess, chunk_size))

    assert all(batches)
    assert [record["winlog"]["record_id"] for batch in batches for record in batch] == [
        1,
        3,
    ]
    assert len(evtx.diagnostics) == 1
    assert evtx.diagnostics[0]["source_file"] == str(evtx.path.resolve())
    assert evtx.diagnostics[0]["stage"] == "normalization"
    assert evtx.diagnostics[0]["record_id"] == 2
    assert evtx.diagnostics[0]["error"].startswith("JSONDecodeError:")


@pytest.fixture
def mixed_input(tmp_path, monkeypatch):
    source = tmp_path / "sample.evtx"
    source.write_bytes(b"fixture")

    class Parser:
        def __init__(self, _file):
            pass

        def records_json(self):
            return iter(
                [
                    raw_record(1),
                    {"event_record_id": 2, "data": "invalid JSON"},
                    raw_record(3),
                ]
            )

    monkeypatch.setattr(model, "PyEvtxParser", Parser)
    return source


def test_public_api_exposes_completed_records_after_normalization_failure(mixed_input):
    with pytest.raises(model.PartialExtractionError) as raised:
        api.evtx2json(str(mixed_input))

    assert [record["winlog"]["record_id"] for record in raised.value.records] == [1, 3]
    assert raised.value.diagnostics[0]["record_id"] == 2


@pytest.mark.parametrize("output_format", ["json", "jsonl"])
def test_json_exports_commit_recovered_records_and_report_partial_failure(
    mixed_input,
    output_format,
):
    target = mixed_input.with_suffix(f".{output_format}")
    presenter = Evtx2jsonPresenter(
        str(mixed_input),
        str(target),
        output_format=output_format,
        is_quiet=True,
    )

    with pytest.raises(model.PartialExtractionError):
        presenter.export_json()

    records = (
        json.loads(target.read_text())
        if output_format == "json"
        else [json.loads(line) for line in target.read_text().splitlines()]
    )
    assert [record["winlog"]["record_id"] for record in records] == [1, 3]
    assert not list(target.parent.glob(f".{target.name}.*.tmp"))


def test_quiet_cli_returns_failure_after_recovered_jsonl_export(
    mixed_input, monkeypatch, capsys
):
    target = mixed_input.with_suffix(".jsonl")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evtx2json",
            str(mixed_input),
            "-o",
            str(target),
            "--format",
            "jsonl",
            "--quiet",
        ],
    )

    with pytest.raises(SystemExit) as raised:
        entry_point()

    assert raised.value.code == 1
    assert len(target.read_text().splitlines()) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert "JSONDecodeError" in output.err
