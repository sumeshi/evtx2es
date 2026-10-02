import importlib
import json
import sys

import pytest

import evtx2es as evtx2es_package
from evtx2es.models.Evtx2es import normalize_tags, process_by_chunk
from evtx2es.views.Evtx2esView import Evtx2esView


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, ["eventlog"]),
        (" eventlog, host01, ,case01,host01 ", ["eventlog", "host01", "case01"]),
        (("host01", " eventlog ", "host01", ""), ["eventlog", "host01"]),
        (["one", "two", "one"], ["eventlog", "one", "two"]),
    ],
)
def test_normalize_tags(value, expected):
    assert normalize_tags(value) == expected


def test_cli_tags_keep_comma_separated_input(monkeypatch):
    monkeypatch.setattr(
        sys, "argv", ["evtx2es", "input.evtx", "--tags", "eventlog, host01,,case01"]
    )
    view = Evtx2esView()
    _, tags = view.get_shift_and_tags()
    assert tags == ["eventlog", "host01", "case01"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("host01, eventlog,host01", ["eventlog", "host01"]),
        (("host01", "eventlog", "case01", "host01"), ["eventlog", "host01", "case01"]),
        ("", ["eventlog"]),
    ],
)
def test_process_by_chunk_normalizes_api_values_without_treating_them_as_generators(
    monkeypatch, value, expected
):
    module = importlib.import_module("evtx2es.models.Evtx2es")
    captured = []

    def fake_format_record(record, filepath, shift, additional_tags):
        captured.append(additional_tags)
        return {"tags": additional_tags}

    monkeypatch.setattr(module, "format_record", fake_format_record)
    assert process_by_chunk([{}], "input.evtx", "0", value) == [{"tags": expected}]
    assert captured == [expected]


def test_process_by_chunk_preserves_internal_generator_path(monkeypatch):
    module = importlib.import_module("evtx2es.models.Evtx2es")
    captured = []
    monkeypatch.setattr(
        module,
        "format_record",
        lambda record, filepath, shift, additional_tags: captured.append(
            additional_tags
        )
        or {"tags": additional_tags},
    )

    def tags():
        yield ("host01", "eventlog")

    result = process_by_chunk([{}], iter(["input.evtx"]), iter(["0"]), tags())
    assert result == [{"tags": ["eventlog", "host01"]}]
    assert captured == [["eventlog", "host01"]]


def test_json_and_jsonl_schema_matches(tmp_path, monkeypatch, raw_record):
    module = importlib.import_module("evtx2es.presenters.Evtx2jsonPresenter")
    model = importlib.import_module("evtx2es.models.Evtx2es")
    record = model.format_record(raw_record, "input.evtx", "0", "host01,eventlog")

    class Model:
        def __init__(self, input_path):
            pass

        def gen_records(self, *args):
            assert args[-1] == "host01,eventlog"
            yield [record]

        def close(self):
            pass

    monkeypatch.setattr(module, "Evtx2es", Model)
    outputs = {}
    for output_format in ("json", "jsonl"):
        presenter = module.Evtx2jsonPresenter(
            str(tmp_path / "input.evtx"),
            str(tmp_path / f"output.{output_format}"),
            is_quiet=True,
            additional_tags="host01,eventlog",
            output_format=output_format,
        )
        presenter.export_json()
        data = presenter.output_path.read_text()
        outputs[output_format] = (
            json.loads(data) if output_format == "json" else [json.loads(data)]
        )
    assert outputs["json"] == outputs["jsonl"] == [record]


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        ("eventlog, host01,eventlog", ["eventlog", "host01"]),
        (["host01", "eventlog", "host01", ""], ["eventlog", "host01"]),
        ((" host01 ", "eventlog", "host01"), ["eventlog", "host01"]),
    ],
)
def test_public_api_formats_tags_from_raw_event(
    tmp_path, monkeypatch, tags, expected, raw_record
):
    model = importlib.import_module("evtx2es.models.Evtx2es")
    source = tmp_path / "sample.evtx"
    source.write_bytes(b"fixture")

    class FakeParser:
        def __init__(self, file_object):
            pass

        def records_json(self):
            return iter([raw_record])

    monkeypatch.setattr(model, "PyEvtxParser", FakeParser)
    records = evtx2es_package.evtx2json(str(source), additional_tags=tags)

    assert len(records) == 1
    assert records[0]["tags"] == expected
    assert records[0]["event"]["dataset"] == "windows.eventlog"


@pytest.fixture
def raw_record():
    return {
        "data": json.dumps(
            {
                "Event": {
                    "System": {
                        "Channel": "Security",
                        "EventID": 4624,
                        "Provider": {
                            "#attributes": {
                                "Name": "Microsoft-Windows-Security-Auditing",
                                "Guid": "{provider-guid}",
                            }
                        },
                        "TimeCreated": {
                            "#attributes": {"SystemTime": "2025-01-02T03:04:05.000000Z"}
                        },
                        "Computer": "HOST01",
                        "EventRecordID": 17,
                        "Task": 12544,
                    },
                    "EventData": {"Message": "日本語", "Values": ["one", "two"]},
                }
            }
        )
    }
