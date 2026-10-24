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


def status_properties(mapping, container="event_data"):
    return mapping["properties"]["winlog"]["properties"][container]["properties"][
        "Status"
    ]


def run_status_cases(client, transport, new_index, stored_documents, document_id, raw):
    documents = status_documents(raw)
    original = deepcopy(documents)
    # Explicit keyword mappings must defeat both date and numeric detection,
    # regardless of which provider/type reaches an initially empty index first.
    for first in (0, 5, 15):
        index = new_index(f"status-shapes-{first}")
        client.indices.create(
            index=index,
            mappings={
                "numeric_detection": True,
                "properties": {
                    "winlog": {
                        "properties": {
                            "event_data_original": {
                                "properties": {"Counter": {"type": "keyword"}}
                            }
                        }
                    }
                },
            },
        )
        ordered = documents[first:] + documents[:first]
        assert transport.bulk_indice(iter(ordered), index) == (len(documents), [])
        actual = stored_documents(client, index)
        assert actual == {document_id(document): document for document in original}
        assert len(actual) == len(documents) and documents == original
        for (status, text), document in zip(STATUS_CASES, original):
            winlog = actual[document_id(document)]["winlog"]
            assert winlog["event_data"]["Status"] == text
            restored = json.loads(winlog["event_data_original"]["Status"])
            assert restored == status and type(restored) is type(status)
            assert winlog["event_data_original"]["Counter"] == str(2**64 - 1)
        mapping = client.indices.get_mapping(index=index)[index]["mappings"]
        for container in ("event_data", "event_data_original"):
            assert status_properties(mapping, container) == {
                "type": "keyword",
                "ignore_above": 8191,
            }
        assert_status_search(client, index, "winlog.event_data.Status", documents)
        # Typed originals also distinguish identical search text (e.g. 0/"0").
        for original_text in {
            doc["winlog"]["event_data_original"]["Status"] for doc in documents
        }:
            assert (
                client.count(
                    index=index,
                    query={
                        "term": {"winlog.event_data_original.Status": original_text}
                    },
                )["count"]
                == 1
            )

    # Legacy null made no field mapping. Retain the old source/document ID and
    # add a keyword field for new records, without silently replacing old data.
    index = new_index("status-legacy-null")
    legacy = deepcopy(documents[3])
    legacy["winlog"]["event_data"]["Status"] = None
    client.index(index=index, id=document_id(legacy), document=legacy, refresh=True)
    before = client.indices.get_mapping(index=index)[index]["mappings"]
    assert (
        "Status"
        not in before["properties"]["winlog"]["properties"]["event_data"]["properties"]
    )
    assert transport.bulk_indice(documents, index) == (len(documents), [])
    actual = stored_documents(client, index)
    assert actual[document_id(legacy)] == legacy
    assert len(actual) == len(documents) + 1
    assert document_id(legacy) != document_id(documents[3])
    assert_status_search(client, index, "winlog.event_data.Status", documents)

    # Existing text mappings remain text. Exact search uses their keyword
    # multifield; adding one does not retroactively index legacy documents.
    index = new_index("status-legacy-text")
    client.indices.create(
        index=index,
        mappings={
            "properties": {
                "winlog": {
                    "properties": {
                        "event_data": {
                            "properties": {
                                "Status": {"type": "text", "analyzer": "whitespace"}
                            }
                        },
                        "event_data_original": {
                            "properties": {
                                "Status": {"type": "text", "analyzer": "whitespace"}
                            }
                        },
                    }
                }
            }
        },
    )
    assert transport.bulk_indice(documents, index) == (len(documents), [])
    actual = stored_documents(client, index)
    assert actual == {document_id(document): document for document in documents}
    mapping = client.indices.get_mapping(index=index)[index]["mappings"]
    assert status_properties(mapping)["type"] == "text"
    assert status_properties(mapping)["analyzer"] == "whitespace"
    assert status_properties(mapping)["fields"]["keyword"]["type"] == "keyword"
    assert_status_search(client, index, "winlog.event_data.Status.keyword", documents)

    # Old numeric/date/object mappings cannot be changed to keyword in place.
    # Reject before bulk instead of coercing "0" or dropping a source value.
    for container in ("event_data", "event_data_original"):
        for kind in ("long", "date", "object"):
            index = new_index(f"status-incompatible-{container}-{kind}")
            client.indices.create(
                index=index,
                mappings={
                    "properties": {
                        "winlog": {
                            "properties": {
                                container: {"properties": {"Status": {"type": kind}}}
                            }
                        }
                    }
                },
            )
            before = client.indices.get_mapping(index=index)[index]["mappings"]
            try:
                transport.bulk_indice(documents, index)
            except Exception as error:
                assert (
                    "Status" in str(error) and "new index" in str(error).lower()
                ), str(error)
            else:
                raise AssertionError(f"Accepted incompatible {container}.Status {kind}")
            assert client.count(index=index)["count"] == 0
            assert client.indices.get_mapping(index=index)[index]["mappings"] == before

    # Keyword length limits must never reject the whole DFIR record or truncate
    # either source field. Long values are retained but omitted from the index.
    index = new_index("status-long")
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
        assert json.loads(document["winlog"]["event_data_original"]["Status"]) == status

    # A new index can inherit disabled/nested objects from a user template.
    # Check the created mapping rather than trusting the create request alone.
    for label, mappings in (
        ("disabled", {"enabled": False}),
        ("nested", {"properties": {"winlog": {"type": "nested"}}}),
    ):
        index = new_index(f"status-template-{label}")
        template = index
        client.indices.put_index_template(
            name=template, index_patterns=[index], template={"mappings": mappings}
        )
        try:
            if label == "nested":
                # An explicit object in the adapter's create body can override
                # the template's nested type. Materialize the inherited nested
                # mapping first so this case exercises an actually nested index.
                client.indices.create(index=index)
                inherited = client.indices.get_mapping(index=index)[index]["mappings"]
                assert inherited["properties"]["winlog"]["type"] == "nested"
            try:
                transport.bulk_indice(documents, index)
            except Exception as error:
                assert (
                    "incompatible" in str(error) and "new index" in str(error).lower()
                ), str(error)
            else:
                raise AssertionError(
                    f"Accepted {label} mapping inherited from template"
                )
            assert client.count(index=index)["count"] == 0
        finally:
            client.indices.delete_index_template(name=template)


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
            assert transport.bulk_indice(documents, index) == (len(documents), [])
            actual = stored_documents(client, index)
            assert actual == {document_id(doc): doc for doc in documents}
            for status, document in zip(fixture["STATUSES"], documents):
                winlog = actual[document_id(document)]["winlog"]
                restored = json.loads(winlog["event_data_original"]["Status"])
                assert restored == status and type(restored) is type(status)
                assert isinstance(winlog["event_data"]["Status"], str)
            assert_status_search(client, index, "winlog.event_data.Status", documents)
        assert sha256(source.read_bytes()).hexdigest() == before
