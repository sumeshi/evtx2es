"""Event evidence and searchable Status exercised against the real ES service."""

from collections import Counter
from copy import deepcopy
import json
from hashlib import sha256
from pathlib import Path
import runpy
from tempfile import TemporaryDirectory

from evtx2es import evtx2json


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

    run_status_cases(client, transport, new_index, stored_documents, document_id, raw)
    run_native_status_cases(client, transport, new_index, stored_documents, document_id)


STATUS_CASES = [
    ("2026-01-01", "2026-01-01"),
    ("0xc000013a", "0xc000013a"),
    ("0xC000013A", "0xC000013A"),
    ("0x20", "0x20"),
    ("0", "0"),
    (0, "0"),
    (-1, "-1"),
    (False, "false"),
    (True, "true"),
    (None, "null"),
    ("false", "false"),
    ("null", "null"),
    ("", ""),
    (1.5, "1.5"),
    (-0.0, "-0.0"),
    ({"Message": "失敗", "Code": "0x20"}, '{"Code":"0x20","Message":"失敗"}'),
    ([0, False, None], "[0,false,null]"),
    ({}, "{}"),
    ([], "[]"),
    (2**64 - 1, "18446744073709551615"),
]


def status_documents(raw):
    documents = []
    for status, _expected in STATUS_CASES:
        event = json.loads(raw["data"])
        event["Event"]["EventData"] = {"Status": status, "Counter": 2**64 - 1}
        record = {**raw, "data": json.dumps(event)}
        documents.append(format_record(record, "generated.evtx", None))
    return documents


def assert_status_search(client, index, field, documents):
    expected = Counter(doc["winlog"]["event_data"]["Status"] for doc in documents)
    for value, count in expected.items():
        hits = client.search(index=index, query={"term": {field: value}}, size=1000)[
            "hits"
        ]["hits"]
        assert len(hits) == count, (field, value, hits)
        assert {hit["_source"]["winlog"]["event_data"]["Status"] for hit in hits} == {
            value
        }
    buckets = client.search(
        index=index,
        size=0,
        aggregations={"statuses": {"terms": {"field": field, "size": 1000}}},
    )["aggregations"]["statuses"]["buckets"]
    assert {bucket["key"]: bucket["doc_count"] for bucket in buckets} == dict(expected)


def status_properties(mapping):
    return mapping["properties"]["winlog"]["properties"]["event_data"]["properties"][
        "Status"
    ]


def status_search_mapping(status=None):
    """Test operator setup; the importer must not provision this mapping."""
    return {
        "properties": {
            "winlog": {
                "properties": {
                    "event_data": {
                        "properties": {
                            "Status": (
                                deepcopy(status)
                                if status is not None
                                else {"type": "keyword", "ignore_above": 8191}
                            )
                        }
                    }
                }
            }
        }
    }


def run_status_cases(client, transport, new_index, stored_documents, document_id, raw):
    documents = status_documents(raw)
    original = deepcopy(documents)
    expected = {document_id(document): document for document in documents}
    # Equal normalized values intentionally share an ID when all metadata is
    # equal: original JSON types are no longer part of the output contract.
    assert len(expected) == len(STATUS_CASES) - 3
    assert document_id(documents[4]) == document_id(documents[5])  # "0" / 0
    assert document_id(documents[7]) == document_id(documents[10])  # false / "false"
    assert document_id(documents[9]) == document_id(documents[11])  # null / "null"
    # The operator supplies keyword mappings before importing. Test both date
    # and numeric detection with different provider/type arrival orders.
    for first in (0, 5, 15):
        index = new_index(f"status-shapes-{first}")
        mappings = status_search_mapping()
        mappings["numeric_detection"] = True
        mappings["properties"]["winlog"]["properties"]["event_data_original"] = {
            "properties": {"Counter": {"type": "keyword"}}
        }
        client.indices.create(index=index, mappings=mappings)
        before = client.indices.get_mapping(index=index)[index]["mappings"]
        ordered = documents[first:] + documents[:first]
        assert transport.bulk_indice(iter(ordered), index) == (len(documents), [])
        actual = stored_documents(client, index)
        assert actual == expected
        assert len(actual) == len(expected) and documents == original
        for (_status, text), document in zip(STATUS_CASES, original):
            winlog = actual[document_id(document)]["winlog"]
            assert winlog["event_data"]["Status"] == text
            assert winlog["event_data_original"] == {"Counter": str(2**64 - 1)}
        after = client.indices.get_mapping(index=index)[index]["mappings"]
        assert (
            status_properties(after)
            == status_properties(before)
            == {"type": "keyword", "ignore_above": 8191}
        )
        assert (
            "Status"
            not in after["properties"]["winlog"]["properties"]["event_data_original"][
                "properties"
            ]
        )
        assert_status_search(
            client, index, "winlog.event_data.Status", expected.values()
        )

    # Legacy null made no field mapping. The operator explicitly provisions the
    # search field before importing new records; old documents remain intact.
    index = new_index("status-legacy-null")
    legacy = deepcopy(documents[3])
    legacy["winlog"]["event_data"]["Status"] = None
    client.index(index=index, id=document_id(legacy), document=legacy, refresh=True)
    before = client.indices.get_mapping(index=index)[index]["mappings"]
    assert (
        "Status"
        not in before["properties"]["winlog"]["properties"]["event_data"]["properties"]
    )
    client.indices.put_mapping(
        index=index, properties=status_search_mapping()["properties"]
    )
    assert transport.bulk_indice(documents, index) == (len(documents), [])
    actual = stored_documents(client, index)
    assert actual[document_id(legacy)] == legacy
    assert len(actual) == len(expected) + 1
    assert document_id(legacy) != document_id(documents[3])
    assert_status_search(client, index, "winlog.event_data.Status", expected.values())

    # Existing text mappings and their operator-defined multifields stay intact.
    # Exact queries use the keyword multifield; the importer must not add one.
    index = new_index("status-legacy-text")
    text = {
        "type": "text",
        "analyzer": "whitespace",
        "fields": {"keyword": {"type": "keyword", "ignore_above": 8191}},
    }
    mappings = status_search_mapping(text)
    mappings["properties"]["winlog"]["properties"]["event_data_original"] = {
        "properties": {"Status": {"type": "text", "analyzer": "whitespace"}}
    }
    client.indices.create(index=index, mappings=mappings)
    before = client.indices.get_mapping(index=index)[index]["mappings"]
    assert transport.bulk_indice(documents, index) == (len(documents), [])
    assert stored_documents(client, index) == expected
    after = client.indices.get_mapping(index=index)[index]["mappings"]
    assert status_properties(after) == status_properties(before) == text
    assert (
        after["properties"]["winlog"]["properties"]["event_data_original"][
            "properties"
        ]["Status"]
        == before["properties"]["winlog"]["properties"]["event_data_original"][
            "properties"
        ]["Status"]
    )
    assert_status_search(
        client, index, "winlog.event_data.Status.keyword", expected.values()
    )

    # An incompatible object mapping is an ordinary Bulk item failure. There
    # is no adapter-side schema validation or repair before sending the records.
    index = new_index("status-incompatible-object")
    client.indices.create(
        index=index, mappings=status_search_mapping({"type": "object"})
    )
    before = client.indices.get_mapping(index=index)[index]["mappings"]
    rejected = {"winlog": {"event_data": {"Status": "0xc000013a"}}}
    healthy = [{"ordinal": 1}, {"ordinal": 2}]
    batch = [healthy[0], rejected, healthy[1]]
    before_batch = deepcopy(batch)
    success, failures = transport.bulk_indice(batch, index)
    assert success == 2 and len(failures) == 1
    assert failures[0]["index"]["status"] == 400
    assert failures[0]["index"]["_id"] == document_id(rejected)
    assert stored_documents(client, index) == {
        document_id(document): document for document in healthy
    }
    after = client.indices.get_mapping(index=index)[index]["mappings"]
    assert status_properties(after) == status_properties(before) == {"type": "object"}
    assert batch == before_batch and documents == original

    # Strings alone do not prevent dynamic date detection. Without an operator
    # mapping, a date-like first Status can make a later NTSTATUS fail in Bulk.
    index = new_index("status-dynamic-date")
    client.indices.create(index=index, mappings={"date_detection": True})
    first, later = documents[:2]
    assert transport.bulk_indice([first], index) == (1, [])
    before = client.indices.get_mapping(index=index)[index]["mappings"]
    assert status_properties(before)["type"] == "date"
    success, failures = transport.bulk_indice([later], index)
    assert success == 0 and len(failures) == 1
    assert failures[0]["index"]["status"] == 400
    assert failures[0]["index"]["_id"] == document_id(later)
    assert stored_documents(client, index) == {document_id(first): first}
    after = client.indices.get_mapping(index=index)[index]["mappings"]
    assert after == before
    assert documents == original

    # Historical original.Status fields are not written or managed. Their old
    # mapping must not block new records or change during a successful import.
    for kind in ("long", "date", "object"):
        index = new_index(f"status-legacy-original-{kind}")
        mappings = status_search_mapping()
        mappings["properties"]["winlog"]["properties"]["event_data_original"] = {
            "properties": {"Status": {"type": kind}}
        }
        client.indices.create(index=index, mappings=mappings)
        before = client.indices.get_mapping(index=index)[index]["mappings"]
        assert transport.bulk_indice(documents, index) == (len(documents), [])
        assert stored_documents(client, index) == expected
        after = client.indices.get_mapping(index=index)[index]["mappings"]
        assert (
            after["properties"]["winlog"]["properties"]["event_data_original"][
                "properties"
            ]["Status"]
            == before["properties"]["winlog"]["properties"]["event_data_original"][
                "properties"
            ]["Status"]
        )
        assert status_properties(after) == status_properties(before)
        assert_status_search(
            client, index, "winlog.event_data.Status", expected.values()
        )

    # The operator's ignore_above setting avoids rejecting an entire record for
    # a huge keyword term. The importer does not truncate the source value.
    index = new_index("status-long")
    client.indices.create(index=index, mappings=status_search_mapping())
    long_documents = []
    for status in ("😀" * 9000, {"Message": "失敗" * 10000}):
        event = json.loads(raw["data"])
        event["Event"]["EventData"] = {"Status": status}
        document = format_record(
            {**raw, "data": json.dumps(event)}, "generated.evtx", None
        )
        long_documents.append(document)
    assert transport.bulk_indice(long_documents, index) == (2, [])
    assert stored_documents(client, index) == {
        document_id(doc): doc for doc in long_documents
    }
    assert (
        client.count(
            index=index, query={"exists": {"field": "winlog.event_data.Status"}}
        )["count"]
        == 0
    )
    for status, document in zip(
        ("😀" * 9000, {"Message": "失敗" * 10000}), long_documents
    ):
        winlog = document["winlog"]
        assert "event_data_original" not in winlog
        value = winlog["event_data"]["Status"]
        assert (
            value == status if isinstance(status, str) else json.loads(value) == status
        )


def run_native_status_cases(
    client, transport, new_index, stored_documents, document_id
):
    fixture = runpy.run_path(str(Path(__file__).with_name("status_fixture.py")))
    with TemporaryDirectory(prefix="evtx-status-es-") as directory:
        source = fixture["create_artifact"](Path(directory))
        before = sha256(source.read_bytes()).hexdigest()
        for multiprocess in (False, True):
            documents = evtx2json(str(source), multiprocess=multiprocess, chunk_size=1)
            assert len(documents) == len(fixture["STATUSES"])
            index = new_index(f"status-native-{multiprocess}".lower())
            client.indices.create(index=index, mappings=status_search_mapping())
            before_mapping = client.indices.get_mapping(index=index)[index]["mappings"]
            assert transport.bulk_indice(documents, index) == (len(documents), [])
            actual = stored_documents(client, index)
            assert actual == {document_id(doc): doc for doc in documents}
            assert len(actual) == len(documents)
            for status, document in zip(fixture["STATUSES"], documents):
                winlog = actual[document_id(document)]["winlog"]
                text = (
                    status
                    if isinstance(status, str)
                    else json.dumps(
                        status,
                        sort_keys=True,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                )
                assert winlog["event_data"]["Status"] == text
                assert isinstance(winlog["event_data"]["Status"], str)
                assert "event_data_original" not in winlog
            assert_status_search(client, index, "winlog.event_data.Status", documents)
            after_mapping = client.indices.get_mapping(index=index)[index]["mappings"]
            assert status_properties(after_mapping) == status_properties(before_mapping)
        assert sha256(source.read_bytes()).hexdigest() == before
