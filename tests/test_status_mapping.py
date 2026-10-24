"""EVTX uses Bulk without inspecting or managing Elasticsearch mappings."""

from copy import deepcopy
from hashlib import sha1
import importlib
from unittest.mock import Mock

import orjson
import pytest

from evtx2es.models.ElasticsearchAdapter import ElasticsearchAdapter
from evtx2es.models.Evtx2es import format_record

module = importlib.import_module("evtx2es.models.ElasticsearchUtils")


def status_record(status, record_id=1):
    return format_record(
        {
            "data": orjson.dumps(
                {
                    "Event": {
                        "System": {
                            "Provider": {"#attributes": {"Name": "Example"}},
                            "EventID": 1,
                            "EventRecordID": record_id,
                        },
                        "EventData": {"Status": status, "Counter": 2**64 - 1},
                    }
                }
            )
        },
        "sample.evtx",
        None,
    )


@pytest.fixture
def bulk_only(monkeypatch):
    # Any attempt to inspect indices, aliases, templates or mappings fails.
    connection = Mock(spec_set=["bulk", "close"])
    monkeypatch.setattr(module, "Elasticsearch", lambda **kwargs: connection)

    def bulk(client, actions, **kwargs):
        assert client is connection
        assert kwargs == {"raise_on_error": False, "stats_only": False}
        return client.bulk(actions)

    monkeypatch.setattr(module, "bulk", bulk)
    helper = module.ElasticsearchUtils("localhost", 9200, "http", "", "")
    return helper, connection


@pytest.mark.parametrize("pipeline", ["", "evidence-pipeline"])
def test_mixed_statuses_use_only_bulk_and_preserve_lazy_sources_ids_and_destination(
    bulk_only, pipeline
):
    helper, connection = bulk_only
    statuses = [
        "0xc000013a",
        "2026-01-01",
        0,
        False,
        None,
        {"Code": "0x20"},
        [0, False, None],
        2**64 - 1,
    ]
    documents = [
        status_record(value, number) for number, value in enumerate(statuses, 1)
    ]
    before = deepcopy(documents)
    consumed = []

    def records():
        for number, document in enumerate(documents):
            consumed.append(number)
            yield document

    def send(actions):
        assert consumed == []
        iterator = iter(actions)
        for number, document in enumerate(before):
            action = next(iterator)
            assert consumed == list(range(number + 1))
            assert action == {
                "_index": "write-alias",
                "_id": sha1(
                    orjson.dumps(document, option=orjson.OPT_SORT_KEYS)
                ).hexdigest(),
                "_source": document,
                **({"pipeline": pipeline} if pipeline else {}),
            }
            assert action["_source"] is documents[number]
            assert type(document["winlog"]["event_data"]["Status"]) is str
            assert document["winlog"]["event_data_original"] == {
                "Counter": str(2**64 - 1)
            }
        with pytest.raises(StopIteration):
            next(iterator)
        return len(documents), []

    connection.bulk.side_effect = send

    assert helper.bulk_indice(records(), "write-alias", pipeline) == (
        len(documents),
        [],
    )
    assert documents == before
    assert [call[0] for call in connection.mock_calls] == ["bulk"]
    helper.close()
    connection.close.assert_called_once_with()


@pytest.mark.parametrize(
    "documents",
    [
        [],
        [{}],
        [{"winlog": {"event_data": {"Counter": 1}}}],
        [{"winlog": {"event_data_original": {"Status": '"legacy"'}}}],
    ],
    ids=["empty", "no-winlog", "no-status", "legacy-original-status"],
)
def test_adapter_passes_records_and_sources_through_without_any_client_api(
    bulk_only, documents
):
    _helper, connection = bulk_only
    adapter = ElasticsearchAdapter(connection)
    records = iter(documents)
    assert adapter.prepare_records(records, "missing-index") is records
    assert list(records) == documents
    for document in documents:
        assert adapter.prepare_source(document) is document
    assert connection.mock_calls == []


def test_mapping_conflicts_are_returned_as_bulk_item_failures(bulk_only):
    helper, connection = bulk_only
    document = status_record("0xc000013a")
    before = deepcopy(document)
    failures = [
        {
            "index": {
                "_id": helper.calc_hash(document),
                "status": 400,
                "error": {
                    "type": "document_parsing_exception",
                    "reason": "mapping conflict",
                },
            }
        }
    ]

    def send(actions):
        (action,) = list(actions)
        assert action["_source"] is document
        assert action["_index"] == "existing-index"
        return 0, failures

    connection.bulk.side_effect = send

    count, actual = helper.bulk_indice([document], "existing-index")
    assert count == 0 and actual is failures
    assert document == before
    assert [call[0] for call in connection.mock_calls] == ["bulk"]


@pytest.mark.parametrize("failure", ["transport", "input"])
def test_bulk_and_input_errors_keep_the_original_cause_without_metadata_access(
    bulk_only, failure
):
    helper, connection = bulk_only
    error = RuntimeError(f"{failure} failed")

    def records():
        yield status_record("0xc000013a")
        if failure == "input":
            raise error

    def send(actions):
        list(actions)
        raise error

    connection.bulk.side_effect = send

    with pytest.raises(Exception, match="Bulk indexing error:") as raised:
        helper.bulk_indice(records(), "existing-index")
    assert raised.value.__cause__ is error
    assert [call[0] for call in connection.mock_calls] == ["bulk"]
