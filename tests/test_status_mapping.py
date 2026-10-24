"""Status mappings must not depend on the first event provider or value."""

from copy import deepcopy
import importlib
from unittest.mock import MagicMock

from elastic_transport import ApiResponseMeta, NodeConfig
from elasticsearch import BadRequestError, NotFoundError
import pytest

from evtx2es.models.ElasticsearchAdapter import STATUS_MAPPING

module = importlib.import_module("evtx2es.models.ElasticsearchUtils")
MISSING = object()
KEYWORD = {"type": "keyword", "ignore_above": 8191}
PROPERTIES = {
    "winlog": {
        "properties": {
            "event_data": {"properties": {"Status": KEYWORD}},
        }
    }
}


def index_info(status=MISSING, original=MISSING, aliases=None):
    properties = {}
    if status is not MISSING:
        properties["event_data"] = {"properties": {"Status": status}}
    if original is not MISSING:
        properties["event_data_original"] = {"properties": {"Status": original}}
    return {
        "aliases": aliases or {},
        "mappings": {"properties": {"winlog": {"properties": properties}}},
    }


def api_error(error_type, status, kind):
    return error_type(
        kind,
        ApiResponseMeta(
            status=status,
            http_version="1.1",
            headers={},
            duration=0,
            node=NodeConfig("http", "localhost", 9200),
        ),
        {"error": {"type": kind}},
    )


@pytest.fixture
def client(monkeypatch):
    connection = MagicMock()
    connection.indices.get.return_value = {"target": index_info(KEYWORD)}
    monkeypatch.setattr(module, "Elasticsearch", lambda **kwargs: connection)
    client = module.ElasticsearchUtils("localhost", 9200, "http", "", "")
    client.sent = []

    def bulk(_connection, actions, **kwargs):
        batch = list(actions)
        client.sent.extend(batch)
        return len(batch), []

    monkeypatch.setattr(module, "bulk", bulk)
    return client


def record(status="0xc000013a"):
    return {
        "winlog": {
            "event_data": {"Status": status},
        }
    }


def test_keyword_mapping_keeps_sources_ids_and_pipeline_and_caches_direct_index(client):
    records = [record(), record("2026-01-01"), record("0")]
    before = deepcopy(records)

    assert client.bulk_indice(iter(records), "target", "evidence") == (3, [])
    assert records == before
    assert [action["_source"] for action in client.sent] == before
    assert [action["_id"] for action in client.sent] == [
        client.calc_hash(r) for r in before
    ]
    assert all(action["pipeline"] == "evidence" for action in client.sent)
    client.es.indices.get.assert_called_once_with(
        index="target", features=["aliases", "mappings"]
    )
    client.es.indices.put_mapping.assert_not_called()
    client.es.indices.create.assert_not_called()
    client.bulk_indice(records[:1], "target")
    client.es.indices.get.assert_called_once()


def test_new_index_gets_only_explicit_search_keyword_mapping(client):
    client.es.indices.get.side_effect = [
        api_error(NotFoundError, 404, "index_not_found_exception"),
        {"target": index_info(KEYWORD)},
    ]

    assert client.bulk_indice([record()], "target") == (1, [])
    client.es.indices.create.assert_called_once_with(
        index="target", mappings={"properties": PROPERTIES}
    )
    client.es.indices.put_mapping.assert_not_called()
    assert STATUS_MAPPING == KEYWORD
    client.bulk_indice([record()], "target")
    assert client.es.indices.get.call_count == 2


@pytest.mark.parametrize("path", ["document", "winlog", "event_data"])
@pytest.mark.parametrize("override", [{"enabled": False}, {"type": "nested"}])
def test_new_index_template_disabled_or_nested_parent_is_rejected(
    client, path, override
):
    info = index_info(KEYWORD)
    if path == "document":
        parent = info["mappings"]
    elif path == "winlog":
        parent = info["mappings"]["properties"]["winlog"]
    else:
        parent = info["mappings"]["properties"]["winlog"]["properties"][path]
    parent.update(override)
    before = deepcopy(info)
    client.es.indices.get.side_effect = [
        api_error(NotFoundError, 404, "index_not_found_exception"),
        {"target": info},
    ]

    with pytest.raises(Exception, match="incompatible.*Use a new index"):
        client.bulk_indice([record()], "target")
    assert client.sent == [] and info == before
    client.es.indices.create.assert_called_once_with(
        index="target", mappings={"properties": PROPERTIES}
    )
    client.es.indices.put_mapping.assert_not_called()
    assert "target" not in client._adapter._status_indices


def test_new_index_metadata_permission_failure_does_not_cache_or_send_status(client):
    error = PermissionError("view_index_metadata required")
    client.es.indices.get.side_effect = [
        api_error(NotFoundError, 404, "index_not_found_exception"),
        error,
    ]

    with pytest.raises(Exception, match="view_index_metadata required") as raised:
        client.bulk_indice([record()], "target")
    assert raised.value.__cause__ is error
    assert client.sent == []
    assert "target" not in client._adapter._status_indices


def test_old_null_did_not_establish_a_mapping_and_search_field_can_be_added(client):
    info = index_info()
    info["mappings"]["properties"]["winlog"]["properties"]["record_id"] = {
        "type": "long"
    }
    client.es.indices.get.return_value = {"target": info}
    before = deepcopy(info)

    assert client.bulk_indice([record()], "target") == (1, [])
    client.es.indices.put_mapping.assert_called_once_with(
        index="target", properties=PROPERTIES
    )
    assert info == before


@pytest.mark.parametrize(
    "existing_type", ["long", "date", "boolean", "object", "alias"]
)
def test_incompatible_mapping_is_rejected_before_any_source_or_mapping_write(
    client, existing_type
):
    info = index_info()
    info["mappings"]["properties"]["winlog"]["properties"]["event_data"] = {
        "properties": {"Status": {"type": existing_type}}
    }
    client.es.indices.get.return_value = {"target": info}
    before = deepcopy(info)

    with pytest.raises(
        Exception, match=r"incompatible winlog\.event_data\.Status.*Use a new index"
    ):
        client.bulk_indice([record()], "target")
    assert client.sent == [] and info == before
    client.es.indices.put_mapping.assert_not_called()
    client.es.indices.create.assert_not_called()


@pytest.mark.parametrize("path", ["document", "winlog", "event_data"])
@pytest.mark.parametrize(
    "mapping", [{"enabled": False}, {"type": "keyword"}, {"type": "nested"}]
)
def test_disabled_or_scalar_parent_is_rejected_without_writes(client, path, mapping):
    info = index_info()
    properties = info["mappings"]["properties"]
    if path == "document":
        info["mappings"] = mapping
    elif path == "winlog":
        properties["winlog"] = mapping
    else:
        properties["winlog"]["properties"][path] = mapping
    client.es.indices.get.return_value = {"target": info}

    with pytest.raises(Exception, match="incompatible.*Use a new index"):
        client.bulk_indice([record()], "target")
    assert client.sent == []
    client.es.indices.put_mapping.assert_not_called()


def test_existing_text_and_its_keyword_multifield_are_preserved(client):
    text = {
        "type": "text",
        "analyzer": "whitespace",
        "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
    }
    info = index_info(text, text)
    before = deepcopy(info)
    client.es.indices.get.return_value = {"target": info}

    assert client.bulk_indice([record()], "target") == (1, [])
    assert info == before
    client.es.indices.put_mapping.assert_not_called()


def test_existing_text_without_keyword_gets_only_an_additional_multifield(client):
    text = {
        "type": "text",
        "analyzer": "whitespace",
        "norms": False,
        "fields": {"raw": {"type": "keyword"}},
    }
    info = index_info(text, KEYWORD)
    before = deepcopy(info)
    client.es.indices.get.return_value = {"target": info}

    assert client.bulk_indice([record()], "target") == (1, [])
    assert info == before
    client.es.indices.put_mapping.assert_called_once_with(
        index="target",
        properties={
            "winlog": {
                "properties": {
                    "event_data": {
                        "properties": {
                            "Status": {
                                "type": "text",
                                "analyzer": "whitespace",
                                "norms": False,
                                "fields": {
                                    "raw": {"type": "keyword"},
                                    "keyword": KEYWORD,
                                },
                            }
                        }
                    }
                }
            }
        },
    )


def test_incompatible_keyword_multifield_is_not_replaced(client):
    text = {"type": "text", "fields": {"keyword": {"type": "long"}}}
    client.es.indices.get.return_value = {"target": index_info(text, KEYWORD)}

    with pytest.raises(Exception, match="Status.keyword.*Use a new index"):
        client.bulk_indice([record()], "target")
    assert client.sent == []
    client.es.indices.put_mapping.assert_not_called()


def test_create_race_rechecks_existing_mapping_instead_of_overwriting(client):
    client.es.indices.get.side_effect = [
        api_error(NotFoundError, 404, "index_not_found_exception"),
        {"target": index_info(KEYWORD)},
    ]
    client.es.indices.create.side_effect = api_error(
        BadRequestError, 400, "resource_already_exists_exception"
    )

    assert client.bulk_indice([record()], "target") == (1, [])
    assert client.es.indices.get.call_count == 2
    client.es.indices.put_mapping.assert_not_called()


def test_create_race_still_rejects_an_incompatible_existing_mapping(client):
    client.es.indices.get.side_effect = [
        api_error(NotFoundError, 404, "index_not_found_exception"),
        {"target": index_info({"type": "long"}, KEYWORD)},
    ]
    client.es.indices.create.side_effect = api_error(
        BadRequestError, 400, "resource_already_exists_exception"
    )

    with pytest.raises(Exception, match="incompatible.*Use a new index"):
        client.bulk_indice([record()], "target")
    assert client.sent == []
    client.es.indices.put_mapping.assert_not_called()


@pytest.mark.parametrize(
    "body", [None, {"error": "invalid"}, {"error": {"type": "other"}}]
)
def test_unrelated_create_errors_are_not_swallowed(client, body):
    error = api_error(BadRequestError, 400, "invalid_mapping")
    error._body = body
    client.es.indices.get.side_effect = api_error(
        NotFoundError, 404, "index_not_found_exception"
    )
    client.es.indices.create.side_effect = error

    with pytest.raises(Exception) as raised:
        client.bulk_indice([record()], "target")
    assert raised.value.__cause__ is error
    assert client.sent == []
    assert client.es.indices.get.call_count == 1


def test_alias_checks_only_its_write_index_and_follows_rollover(client):
    client.es.indices.get.side_effect = [
        {
            "old": index_info(
                {"type": "long"}, aliases={"target": {"is_write_index": False}}
            ),
            "current": index_info(aliases={"target": {"is_write_index": True}}),
        },
        {"next": index_info(aliases={"target": {"is_write_index": True}})},
    ]

    client.bulk_indice([record()], "target")
    client.bulk_indice([record()], "target")
    assert [
        call.kwargs["index"] for call in client.es.indices.put_mapping.call_args_list
    ] == ["current", "next"]
    assert [action["_index"] for action in client.sent] == ["target", "target"]


def test_single_index_alias_without_an_explicit_write_flag_is_supported(client):
    client.es.indices.get.return_value = {
        "backing": index_info(KEYWORD, KEYWORD, aliases={"target": {}})
    }

    assert client.bulk_indice([record()], "target") == (1, [])
    client.bulk_indice([record()], "target")
    assert client.es.indices.get.call_count == 2
    client.es.indices.put_mapping.assert_not_called()


@pytest.mark.parametrize(
    "aliases",
    [
        {"one": {}, "two": {}},
        {"one": {"is_write_index": False}},
        {"one": {"is_write_index": True}, "two": {"is_write_index": True}},
    ],
)
def test_ambiguous_or_nonwritable_alias_does_not_modify_indices(client, aliases):
    client.es.indices.get.return_value = {
        name: index_info(aliases={"target": flags}) for name, flags in aliases.items()
    }

    with pytest.raises(Exception, match="Cannot determine one write index"):
        client.bulk_indice([record()], "target")
    assert client.sent == []
    client.es.indices.put_mapping.assert_not_called()
    client.es.indices.create.assert_not_called()


def test_status_free_records_do_not_require_mapping_permissions(client):
    records = [
        {},
        {"winlog": {"event_data": {"Counter": 1}}},
        {"ordinal": 1},
        {"winlog": {"event_data_original": {"Counter": str(2**64 - 1)}}},
    ]

    assert client.bulk_indice(iter(records), "target") == (4, [])
    client.es.indices.get.assert_not_called()
    client.es.indices.create.assert_not_called()
    client.es.indices.put_mapping.assert_not_called()


def test_empty_input_does_not_require_mapping_permissions(client):
    assert client.bulk_indice(iter(()), "target") == (0, [])
    client.es.indices.get.assert_not_called()


def test_legacy_status_only_in_original_does_not_prepare_a_mapping(client):
    document = {"winlog": {"event_data_original": {"Status": '"0"'}}}
    assert client.bulk_indice([document], "target") == (1, [])
    client.es.indices.get.assert_not_called()
    client.es.indices.put_mapping.assert_not_called()
    client.es.indices.create.assert_not_called()


def test_permission_failure_is_reported_before_any_status_is_sent(client):
    client.es.indices.get.side_effect = PermissionError("view_index_metadata required")

    with pytest.raises(Exception, match="view_index_metadata required"):
        client.bulk_indice([record()], "target")
    assert client.sent == []
    client.es.indices.put_mapping.assert_not_called()
    client.es.indices.create.assert_not_called()


@pytest.mark.parametrize("existing_type", ["long", "date", "boolean", "object", "text"])
@pytest.mark.parametrize("search_mapping_present", [False, True])
def test_legacy_original_status_mapping_is_not_validated_or_modified(
    client, existing_type, search_mapping_present
):
    info = index_info(
        KEYWORD if search_mapping_present else MISSING,
        {"type": existing_type},
    )
    before = deepcopy(info)
    client.es.indices.get.return_value = {"target": info}

    assert client.bulk_indice([record()], "target") == (1, [])

    assert info == before
    if search_mapping_present:
        client.es.indices.put_mapping.assert_not_called()
    else:
        client.es.indices.put_mapping.assert_called_once_with(
            index="target", properties=PROPERTIES
        )
    assert client.sent[0]["_source"] == record()


@pytest.mark.parametrize(
    "original_parent", [{"enabled": False}, {"type": "nested"}, {"type": "keyword"}]
)
@pytest.mark.parametrize("new_index", [False, True])
def test_legacy_original_parent_is_not_validated_or_modified(
    client, original_parent, new_index
):
    info = index_info(KEYWORD)
    info["mappings"]["properties"]["winlog"]["properties"][
        "event_data_original"
    ] = original_parent
    before = deepcopy(info)
    if new_index:
        client.es.indices.get.side_effect = [
            api_error(NotFoundError, 404, "index_not_found_exception"),
            {"target": info},
        ]
    else:
        client.es.indices.get.return_value = {"target": info}

    assert client.bulk_indice([record()], "target") == (1, [])

    assert info == before
    client.es.indices.put_mapping.assert_not_called()
    if new_index:
        client.es.indices.create.assert_called_once_with(
            index="target", mappings={"properties": PROPERTIES}
        )
    else:
        client.es.indices.create.assert_not_called()


def test_unrelated_original_values_are_sent_unchanged(client):
    document = record()
    document["winlog"]["event_data_original"] = {"Counter": str(2**64 - 1)}
    before = deepcopy(document)

    assert client.bulk_indice([document], "target") == (1, [])

    assert document == before
    assert client.sent[0]["_source"] == before
    assert client.sent[0]["_id"] == client.calc_hash(before)
    client.es.indices.put_mapping.assert_not_called()
