"""Exercise CLI timestamp shifting through the formatter and real workers."""

from datetime import datetime
import importlib
import multiprocessing
import os
import sys

import orjson
import pytest

from evtx2es.models.Evtx2es import _mp_worker


def _format_in_spawn_worker(arguments):
    assert multiprocessing.parent_process() is not None
    assert multiprocessing.get_start_method() == "spawn"
    return _mp_worker(arguments)


@pytest.mark.parametrize("multiprocess", [False, True], ids=["single", "spawn"])
@pytest.mark.parametrize("destination", ["json", "jsonl", "es"])
def test_datasetdate_reaches_formatter_and_preserves_raw_time(
    tmp_path, monkeypatch, destination, multiprocess
):
    model = importlib.import_module("evtx2es.models.Evtx2es")
    base_view = importlib.import_module("evtx2es.views.BaseView")
    source = tmp_path / "synthetic.evtx"
    source.write_bytes(b"synthetic parser input")
    caller_pid = os.getpid()
    raw_times = [
        "2025-01-02T03:04:05.1234567+02:00",
        "2025-01-02T03:04:06.7654321+02:00",
    ]

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2025, 1, 2, 3, 4, 5, 250000, tzinfo=tz)

    class Parser:
        def __init__(self, file_object):
            assert file_object.name == str(source)

        def records_json(self):
            for record_id, raw_time in enumerate(raw_times, start=1):
                assert os.getpid() == caller_pid
                yield {
                    "data": orjson.dumps(
                        {
                            "Event": {
                                "System": {
                                    "Channel": "Security",
                                    "EventID": 4624,
                                    "Provider": {"#attributes": {"Name": "Provider"}},
                                    "TimeCreated": {
                                        "#attributes": {"SystemTime": raw_time}
                                    },
                                    "Computer": "HOST01",
                                    "EventRecordID": record_id,
                                    "Task": 12544,
                                },
                            },
                        }
                    ),
                }

    monkeypatch.setattr(base_view, "datetime", FixedDateTime)
    monkeypatch.setattr(model, "PyEvtxParser", Parser)
    monkeypatch.setattr(model.Evtx2es, "get_cpu_count", staticmethod(lambda: 2))
    if multiprocess:
        monkeypatch.setattr(model, "_mp_worker", _format_in_spawn_worker)

    command = "evtx2es" if destination == "es" else "evtx2json"
    arguments = [
        command,
        str(source),
        "--datasetdate",
        "01/02/2025.03:04:07",
        "--size",
        "1",
        "--quiet",
    ]
    if multiprocess:
        arguments.append("--multiprocess")
    documents = []
    closed = []
    if destination == "es":
        presenter = importlib.import_module("evtx2es.presenters.Evtx2esPresenter")

        class Elasticsearch:
            def __init__(self, **kwargs):
                pass

            def bulk_indice(self, records, index, pipeline):
                documents.extend(records)
                return len(records), []

            def close(self):
                closed.append(True)

        monkeypatch.setattr(presenter, "ElasticsearchUtils", Elasticsearch)
    else:
        output = tmp_path / f"export.{destination}"
        arguments.extend(["--format", destination, "-o", str(output)])
    monkeypatch.setattr(sys, "argv", arguments)
    view = "Evtx2esView" if destination == "es" else "Evtx2jsonView"
    importlib.import_module(f"evtx2es.views.{view}").entry_point()

    if destination == "json":
        documents = orjson.loads(output.read_bytes())
    elif destination == "jsonl":
        documents = [orjson.loads(line) for line in output.read_bytes().splitlines()]
    else:
        assert closed == [True]
    # The fixed UTC clock produces a negative 1.75-second shift.
    assert [doc["@timestamp"] for doc in documents] == [
        "2025-01-02T01:04:03.3734567Z",
        "2025-01-02T01:04:05.0154321Z",
    ]
    assert [doc["event"]["created"] for doc in documents] == raw_times
    assert [doc["winlog"]["record_id"] for doc in documents] == [1, 2]
    assert [doc["log"]["file"]["path"] for doc in documents] == [str(source)] * 2
