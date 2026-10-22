import json

import pytest

from evtx2es.models.ElasticsearchUtils import ElasticsearchUtils
from evtx2es.models.Evtx2es import _create_normalized_event_data, format_record


def raw_record(event_data):
    return {
        "event_record_id": 1,
        "data": json.dumps(
            {
                "Event": {
                    "System": {
                        "Provider": {"#attributes": {"Name": "Example"}},
                        "EventID": 1,
                        "Channel": "Application",
                        "Task": 0,
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
    "value",
    [-(2**63) - 1, -(2**63), -1, 0, 2**63 - 1, 2**63, 2**64 - 1],
)
def test_clamped_integer_can_be_recovered_exactly(value):
    original = {}
    data = {"Counter": value}

    normalized = _create_normalized_event_data(data, original)

    expected = min(max(value, -(2**63)), 2**63 - 1)
    assert normalized == {"Counter": expected}
    if value != expected:
        assert original == {"Counter": str(value)}
        assert int(original["Counter"]) == value
    else:
        assert original == {}
    assert data == {"Counter": value}


def test_distinct_unsigned_values_remain_distinct_in_documents_and_ids():
    values = [2**63, 2**64 - 1]
    documents = [
        format_record(raw_record({"Counter": v}), "sample.evtx", None) for v in values
    ]

    assert [doc["winlog"]["event_data"]["Counter"] for doc in documents] == [
        2**63 - 1
    ] * 2
    assert [doc["winlog"]["event_data_original"]["Counter"] for doc in documents] == [
        str(value) for value in values
    ]
    es = ElasticsearchUtils.__new__(ElasticsearchUtils)
    assert es.calc_hash(documents[0]) != es.calc_hash(documents[1])
    for document in documents:
        del document["winlog"]["event_data_original"]
    assert documents[0] == documents[1]


def test_existing_lossless_fields_do_not_gain_original_values():
    data = {
        "Reason": 2**63,
        "ProcessId": "0x10",
        "Counter": 2**63 - 1,
        "Enabled": True,
        "Disabled": False,
        "Nested": {"Counter": 2**63},
    }

    document = format_record(raw_record(data), "sample.evtx", None)

    assert document["winlog"]["event_data"] == {
        **data,
        "Reason": str(2**63),
        "ProcessId": 16,
    }
    assert "event_data_original" not in document["winlog"]
