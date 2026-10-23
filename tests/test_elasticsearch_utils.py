"""The transport contract shared by all artifact importers."""

from copy import deepcopy
from hashlib import sha1
import importlib
from pathlib import Path
import tomllib
from unittest.mock import MagicMock

import pytest

PACKAGE = tomllib.loads(
    (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text()
)["project"]["name"]
module = importlib.import_module(f"{PACKAGE}.models.ElasticsearchUtils")


@pytest.fixture
def connection(monkeypatch):
    client = MagicMock()
    factory = MagicMock(return_value=client)
    monkeypatch.setattr(module, "Elasticsearch", factory)
    return client, factory


@pytest.mark.parametrize(
    "login,password,verify,ca",
    [
        ("", "", True, None),
        ("user", "", True, "ca.pem"),
        ("user", "secret", False, None),
    ],
)
def test_connection_options_and_close(connection, login, password, verify, ca):
    client, factory = connection
    helper = module.ElasticsearchUtils(
        "example",
        9243,
        "https",
        login,
        password,
        verify_certs=verify,
        ca_certs=ca,
    )
    expected = {"hosts": ["https://example:9243"], "verify_certs": verify}
    if login:
        expected["basic_auth"] = (login, password)
    if ca is not None:
        expected["ca_certs"] = ca
    factory.assert_called_once_with(**expected)
    helper.close()
    client.close.assert_called_once_with()


@pytest.mark.parametrize("pipeline", ["", "normalize-events"])
def test_bulk_is_lazy_and_keeps_original_sources_and_sorted_ids(
    connection, monkeypatch, pipeline
):
    client, _factory = connection
    helper = module.ElasticsearchUtils("localhost", 9200, "http", "", "")
    records = [{"z": index, "a": "日本語"} for index in range(3)]
    before = deepcopy(records)
    consumed = []

    def inputs():
        for index, record in enumerate(records):
            consumed.append(index)
            yield record

    def bulk(es, actions, **kwargs):
        assert es is client
        assert kwargs == {"raise_on_error": False, "stats_only": False}
        assert consumed == []
        iterator = iter(actions)
        for index, record in enumerate(before):
            action = next(iterator)
            assert consumed == list(range(index + 1))
            expected_json = ('{"a":"日本語","z":' + str(index) + "}").encode()
            assert action == {
                "_id": sha1(expected_json).hexdigest(),
                "_index": "events",
                "_source": record,
                **({"pipeline": pipeline} if pipeline else {}),
            }
        with pytest.raises(StopIteration):
            next(iterator)
        return len(before), []

    monkeypatch.setattr(module, "bulk", bulk)
    assert helper.bulk_indice(inputs(), "events", pipeline) == (3, [])
    assert records == before


def test_bulk_default_pipeline_and_item_failures_are_returned(connection, monkeypatch):
    helper = module.ElasticsearchUtils("localhost", 9200, "http", "", "")
    failures = [{"index": {"_id": "bad", "status": 400}}]

    def bulk(_client, actions, **kwargs):
        assert "pipeline" not in next(iter(actions))
        return 0, failures

    monkeypatch.setattr(module, "bulk", bulk)
    count, actual_failures = helper.bulk_indice([{"id": 1}], "events")
    assert count == 0
    assert actual_failures is failures


@pytest.mark.parametrize("failure", ["transport", "input"])
def test_bulk_errors_preserve_the_cause(connection, monkeypatch, failure):
    helper = module.ElasticsearchUtils("localhost", 9200, "http", "", "")
    original = RuntimeError(
        "transport unavailable" if failure == "transport" else "input failed"
    )

    def inputs():
        raise original
        yield  # This remains a lazy iterator without producing a document.

    def bulk(_client, actions, **kwargs):
        if failure == "transport":
            raise original
        list(actions)

    monkeypatch.setattr(module, "bulk", bulk)
    with pytest.raises(Exception, match="Bulk indexing error:") as error:
        helper.bulk_indice(inputs(), "events")
    assert error.value.__cause__ is original
