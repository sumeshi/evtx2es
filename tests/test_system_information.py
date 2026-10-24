import copy
import json

import pytest

from evtx2es.models.ElasticsearchUtils import ElasticsearchUtils
from evtx2es.models.Evtx2es import format_record, process_by_chunk


def raw_record(**system_fields):
    # Shapes emitted by evtx 0.13.1 for CAPI2 and RdpCoreTS native samples.
    system = {
        "Provider": {"#attributes": {"Name": "Microsoft-Windows-CAPI2"}},
        "EventID": 11,
        "Channel": "Microsoft-Windows-CAPI2/Operational",
        "EventRecordID": 1,
        "Computer": "HOST01",
        "TimeCreated": {"#attributes": {"SystemTime": "2018-08-05T10:34:37Z"}},
        "Task": 0,
        **system_fields,
    }
    return {"event_record_id": 1, "data": json.dumps({"Event": {"System": system}})}


def test_preserves_system_identity_and_raw_level_and_keywords():
    record = raw_record(
        Security={"#attributes": {"UserID": "S-1-5-20"}},
        Correlation={
            "#attributes": {
                "ActivityID": "F42004DA-7659-4B1E-B263-BE994EC80000",
                "RelatedActivityID": "{00000000-0000-0000-0000-000000000001}",
            }
        },
        Level=0,
        Keywords="0x8000000000000000",
    )
    original = copy.deepcopy(record)

    document = format_record(record, "sample.evtx", None)

    assert document["winlog"]["user"]["identifier"] == "S-1-5-20"
    assert document["winlog"]["activity_id"] == "F42004DA-7659-4B1E-B263-BE994EC80000"
    assert document["winlog"]["related_activity_id"] == (
        "{00000000-0000-0000-0000-000000000001}"
    )
    assert document["winlog"]["level"] == 0
    assert document["winlog"]["keywords"] == "0x8000000000000000"
    assert record == original

    for key in ("user", "activity_id", "related_activity_id", "level", "keywords"):
        del document["winlog"][key]
    assert document == format_record(raw_record(), "sample.evtx", None)


@pytest.mark.parametrize(
    "system_fields",
    [
        {},
        {"Security": None, "Correlation": None},
        {"Security": {}, "Correlation": {}},
        {"Security": {"#attributes": None}, "Correlation": {"#attributes": None}},
        {"Security": {"#attributes": {}}, "Correlation": {"#attributes": {}}},
        {"Security": "unrecognized", "Correlation": []},
        {"Security": {"#attributes": []}, "Correlation": {"#attributes": 1}},
    ],
)
def test_unavailable_optional_identity_does_not_drop_event_or_invent_values(system_fields):
    diagnostics = []

    documents = process_by_chunk(
        [raw_record(**system_fields)],
        "sample.evtx",
        None,
        on_record_error=diagnostics.append,
    )

    assert documents == [format_record(raw_record(), "sample.evtx", None)]
    assert diagnostics == []


@pytest.mark.parametrize(
    "first,second",
    [
        (
            {"Security": {"#attributes": {"UserID": "S-1-5-18"}}},
            {"Security": {"#attributes": {"UserID": "S-1-5-20"}}},
        ),
        (
            {"Correlation": {"#attributes": {"ActivityID": "activity-a"}}},
            {"Correlation": {"#attributes": {"ActivityID": "activity-b"}}},
        ),
        (
            {"Correlation": {"#attributes": {"RelatedActivityID": "parent-a"}}},
            {"Correlation": {"#attributes": {"RelatedActivityID": "parent-b"}}},
        ),
        ({"Level": 0}, {"Level": 4}),
        ({"Keywords": "0x0"}, {"Keywords": "0x8000000000000000"}),
    ],
)
def test_distinct_system_information_remains_distinguishable_in_documents_and_ids(
    first, second
):
    documents = [
        format_record(raw_record(**fields), "sample.evtx", None)
        for fields in (first, second)
    ]
    es = ElasticsearchUtils.__new__(ElasticsearchUtils)

    assert documents[0] != documents[1]
    assert es.calc_hash(documents[0]) != es.calc_hash(documents[1])
