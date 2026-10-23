"""Status keeps its original JSON value without changing its legacy null field."""

from copy import deepcopy
import json

import pytest

from evtx2es.models.ElasticsearchUtils import ElasticsearchUtils
from evtx2es.models.Evtx2es import (
    _create_normalized_event_data,
    _parse_event_data,
    format_record,
)


def raw_record(event_data):
    return {
        "event_record_id": 1,
        "data": json.dumps(
            {
                "Event": {
                    "System": {
                        "Provider": {"#attributes": {"Name": "Example"}},
                        "EventID": 1,
                        "Channel": "Security",
                        "EventRecordID": 1,
                        "TimeCreated": {
                            "#attributes": {"SystemTime": "2026-01-01T00:00:00Z"}
                        },
                    },
                    "EventData": event_data,
                }
            }
        ),
    }


@pytest.mark.parametrize(
    "status",
    [
        "0x20",
        "0xc000013a",
        "0",
        0,
        False,
        True,
        None,
        2**64 - 1,
        {"Code": "0x20", "Message": "失敗"},
        [0, False, None, {"Code": "0x20"}],
    ],
)
def test_status_round_trip_preserves_value_and_type_with_legacy_null(status):
    record = raw_record({"Status": status})
    before = deepcopy(record)

    document = format_record(record, "sample.evtx", None)

    assert document["winlog"]["event_data"] == {"Status": None}
    original = document["winlog"]["event_data_original"]["Status"]
    assert isinstance(original, str)
    restored = json.loads(original)
    assert restored == status and type(restored) is type(status)
    assert record == before


def test_parse_keeps_status_until_normalization():
    record = raw_record({"Status": {"Code": "0x20"}})

    parsed = _parse_event_data(record)

    assert parsed["event_data"] == {"Status": {"Code": "0x20"}}


def test_status_preservation_does_not_mutate_event_data():
    data = {"Status": {"Code": "0x20"}, "Counter": 2**64 - 1}
    before = deepcopy(data)
    originals = {}

    normalized = _create_normalized_event_data(data, originals)

    assert normalized == {"Status": None, "Counter": 2**63 - 1}
    assert json.loads(originals["Status"]) == data["Status"]
    assert originals["Counter"] == str(2**64 - 1)
    assert data == before


def test_absent_status_does_not_add_a_sidecar():
    document = format_record(raw_record({"Message": "normal"}), "sample.evtx", None)

    assert document["winlog"]["event_data"] == {"Message": "normal"}
    assert "event_data_original" not in document["winlog"]


def test_distinct_status_values_and_types_have_distinct_ids():
    statuses = ["0", 0, False, None, "null", "false", {}, []]
    documents = [
        format_record(raw_record({"Status": status}), "sample.evtx", None)
        for status in statuses
    ]
    transport = ElasticsearchUtils.__new__(ElasticsearchUtils)

    assert len({transport.calc_hash(document) for document in documents}) == len(
        statuses
    )
    for document in documents:
        del document["winlog"]["event_data_original"]
    assert all(document == documents[0] for document in documents)


def test_status_object_key_order_keeps_the_same_id_and_array_order():
    statuses = [
        {"Message": "失敗", "Details": [{"Retry": False, "Code": 0}, None]},
        {"Details": [{"Code": 0, "Retry": False}, None], "Message": "失敗"},
    ]
    documents = [
        format_record(raw_record({"Status": status}), "sample.evtx", None)
        for status in statuses
    ]
    transport = ElasticsearchUtils.__new__(ElasticsearchUtils)

    assert documents[0] == documents[1]
    assert transport.calc_hash(documents[0]) == transport.calc_hash(documents[1])
    for status, document in zip(statuses, documents):
        restored = json.loads(document["winlog"]["event_data_original"]["Status"])
        assert restored == status
        assert type(restored["Details"][0]["Code"]) is int
        assert type(restored["Details"][0]["Retry"]) is bool

    reordered = deepcopy(statuses[0])
    reordered["Details"].reverse()
    document = format_record(raw_record({"Status": reordered}), "sample.evtx", None)
    assert transport.calc_hash(document) != transport.calc_hash(documents[0])
    assert json.loads(document["winlog"]["event_data_original"]["Status"]) == reordered
