"""Event identity and integer evidence exercised against the real ES service."""

from copy import deepcopy
import json

from evtx2es.models.Evtx2es import format_record


def expected_source(document):
    return deepcopy(document)


def assert_native_documents(documents, mode):
    assert mode is None and len(documents) == 3
    assert [document["winlog"]["record_id"] for document in documents] == [
        227126,
        227127,
        227128,
    ]
    originals = [
        document["winlog"]["event_data_original"]["SubjectLogonId"]
        for document in documents
        if "event_data_original" in document["winlog"]
    ]
    assert originals == [str(2**63), str(2**64 - 1)]


def run_extra_cases(client, transport, new_index, stored_documents, document_id):
    documents = []
    for value in (2**63, 2**64 - 1):
        raw = {
            "event_record_id": 1,
            "data": json.dumps(
                {
                    "Event": {
                        "System": {
                            "Provider": {"#attributes": {"Name": "CI-Event"}},
                            "EventID": 1,
                            "Channel": "Application",
                            "EventRecordID": 1,
                            "TimeCreated": {
                                "#attributes": {"SystemTime": "2026-01-01T00:00:00Z"}
                            },
                            "Security": {"#attributes": {"UserID": "S-1-5-20"}},
                            "Correlation": {
                                "#attributes": {
                                    "ActivityID": "00000000-0000-0000-0000-000000000001",
                                    "RelatedActivityID": "00000000-0000-0000-0000-000000000002",
                                }
                            },
                            "Level": 0,
                            "Keywords": "0x8000000000000000",
                        },
                        "EventData": {"Counter": value},
                    }
                }
            ),
        }
        documents.append(format_record(raw, "generated.evtx", None))
    original = deepcopy(documents)
    index = new_index("identity-and-integers")
    assert transport.bulk_indice(documents, index) == (2, [])
    actual = stored_documents(client, index)
    assert actual == {document_id(document): document for document in original}
    assert len(actual) == 2 and documents == original
    for document in actual.values():
        winlog = document["winlog"]
        assert winlog["event_data"]["Counter"] == 2**63 - 1
        assert winlog["user"]["identifier"] == "S-1-5-20"
        assert winlog["activity_id"] == "00000000-0000-0000-0000-000000000001"
        assert winlog["related_activity_id"] == "00000000-0000-0000-0000-000000000002"
        assert winlog["level"] == 0 and winlog["keywords"] == "0x8000000000000000"
        assert winlog["task"] is None
    assert {
        document["winlog"]["event_data_original"]["Counter"]
        for document in actual.values()
    } == {str(2**63), str(2**64 - 1)}

    # Event providers use different Status value shapes. Keep one ES text
    # mapping while retaining the JSON type and distinguishing identical text.
    statuses = [
        "0x20",
        "0",
        0,
        False,
        None,
        "false",
        "null",
        {"Code": "0x20", "Message": "失敗"},
        [0, False, None],
        2**64 - 1,
    ]
    documents = []
    for status in statuses:
        event = json.loads(raw["data"])
        event["Event"]["EventData"] = {"Status": status, "Counter": 2**64 - 1}
        record = {**raw, "data": json.dumps(event)}
        documents.append(format_record(record, "generated.evtx", None))
    original = deepcopy(documents)
    index = new_index("status-shapes")
    assert transport.bulk_indice(documents, index) == (len(statuses), [])
    actual = stored_documents(client, index)
    assert actual == {document_id(document): document for document in original}
    assert len(actual) == len(statuses) and documents == original
    for status, document in zip(statuses, original):
        winlog = actual[document_id(document)]["winlog"]
        assert winlog["event_data"]["Status"] is None
        restored = json.loads(winlog["event_data_original"]["Status"])
        assert restored == status and type(restored) is type(status)
        assert winlog["event_data_original"]["Counter"] == str(2**64 - 1)
    mapping = client.indices.get_mapping(index=index)[index]["mappings"][
        "properties"
    ]["winlog"]["properties"]["event_data_original"]["properties"]["Status"]
    assert mapping["type"] in {"text", "keyword"}
