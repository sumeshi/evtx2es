"""Status is searchable text without a duplicate original field."""

from copy import deepcopy
import json
import math

import orjson
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
    "status, expected",
    [
        ("0x20", "0x20"),
        ("0xC000013A", "0xC000013A"),
        ("0xc000013a", "0xc000013a"),
        ("0", "0"),
        ("false", "false"),
        ("null", "null"),
        ("", ""),
        (" 0x20\n", " 0x20\n"),
        ('失敗\u0000"', '失敗\u0000"'),
        ("2026-01-01", "2026-01-01"),
        (0, "0"),
        (-1, "-1"),
        (False, "false"),
        (True, "true"),
        (None, "null"),
        (2**64 - 1, "18446744073709551615"),
        (-(2**63), "-9223372036854775808"),
        (1.5, "1.5"),
        (-0.0, "-0.0"),
        ({"Message": "失敗", "Code": "0x20"}, '{"Code":"0x20","Message":"失敗"}'),
        ([0, False, None, {"Code": "0x20"}], '[0,false,null,{"Code":"0x20"}]'),
        ({}, "{}"),
        ([], "[]"),
    ],
)
def test_status_search_text_without_an_original_duplicate(status, expected):
    record = raw_record({"Status": status})
    before = deepcopy(record)

    document = format_record(record, "sample.evtx", None)

    assert document["winlog"]["event_data"] == {"Status": expected}
    assert "event_data_original" not in document["winlog"]
    if not isinstance(status, str):
        restored = json.loads(document["winlog"]["event_data"]["Status"])
        assert restored == status
    if type(status) is float:
        assert math.copysign(1, restored) == math.copysign(1, status)
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

    assert normalized == {"Status": '{"Code":"0x20"}', "Counter": 2**63 - 1}
    assert originals == {"Counter": str(2**64 - 1)}
    assert data == before


def test_absent_status_does_not_add_a_sidecar():
    document = format_record(raw_record({"Message": "normal"}), "sample.evtx", None)

    assert document["winlog"]["event_data"] == {"Message": "normal"}
    assert "event_data_original" not in document["winlog"]


def test_equivalent_status_text_shares_ids_regardless_of_source_json_type():
    statuses = ["0", 0, False, None, "null", "false", {}, []]
    documents = [
        format_record(raw_record({"Status": status}), "sample.evtx", None)
        for status in statuses
    ]
    transport = ElasticsearchUtils.__new__(ElasticsearchUtils)

    assert len({transport.calc_hash(document) for document in documents}) == 5
    for left, right in ((0, 1), (2, 5), (3, 4)):
        assert documents[left] == documents[right]
        assert transport.calc_hash(documents[left]) == transport.calc_hash(
            documents[right]
        )


def test_status_changes_ids_from_the_legacy_null_and_previous_duplicate():
    document = format_record(raw_record({"Status": "0x20"}), "sample.evtx", None)
    previous = deepcopy(document)
    previous["winlog"]["event_data"]["Status"] = None
    transport = ElasticsearchUtils.__new__(ElasticsearchUtils)

    assert transport.calc_hash(document) != transport.calc_hash(previous)
    previous = deepcopy(document)
    previous["winlog"]["event_data_original"] = {"Status": '"0x20"'}
    assert transport.calc_hash(document) != transport.calc_hash(previous)


@pytest.mark.parametrize(
    "status",
    ["😀" * 9000, {"Message": "失敗" * 10000}],
    ids=["long-string", "long-object"],
)
def test_long_status_is_not_truncated_in_json_outputs(status):
    document = format_record(raw_record({"Status": status}), "sample.evtx", None)

    for payload in (orjson.dumps([document]), orjson.dumps(document) + b"\n"):
        restored = orjson.loads(payload)
        result = restored[0] if isinstance(restored, list) else restored
        assert result == document
        text = result["winlog"]["event_data"]["Status"]
        assert (text if isinstance(status, str) else json.loads(text)) == status
        assert "event_data_original" not in result["winlog"]


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
        restored = json.loads(document["winlog"]["event_data"]["Status"])
        assert restored == status
        assert type(restored["Details"][0]["Code"]) is int
        assert type(restored["Details"][0]["Retry"]) is bool

    reordered = deepcopy(statuses[0])
    reordered["Details"].reverse()
    document = format_record(raw_record({"Status": reordered}), "sample.evtx", None)
    assert transport.calc_hash(document) != transport.calc_hash(documents[0])
    assert json.loads(document["winlog"]["event_data"]["Status"]) == reordered
