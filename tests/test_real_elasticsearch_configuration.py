"""An explicit real-ES test request must never silently become a skip."""

import importlib.util
from pathlib import Path

from elastic_transport import ConnectionError
import pytest


def load_integration_module():
    path = Path(__file__).with_name("test_real_elasticsearch.py")
    spec = importlib.util.spec_from_file_location("real_es_configuration_target", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_unconfigured_real_es_is_opt_in(monkeypatch):
    monkeypatch.delenv("ELASTICSEARCH_URL", raising=False)
    module = load_integration_module()
    fixture = module.real_es.__wrapped__()
    with pytest.raises(pytest.skip.Exception, match="Set ELASTICSEARCH_URL"):
        next(fixture)


@pytest.mark.parametrize("url", ["", "not-a-url", "file:///tmp/elasticsearch"])
def test_explicit_invalid_real_es_url_fails(monkeypatch, url):
    monkeypatch.setenv("ELASTICSEARCH_URL", url)
    module = load_integration_module()
    fixture = module.real_es.__wrapped__()
    with pytest.raises(pytest.fail.Exception, match="nonempty http"):
        next(fixture)


def test_explicit_unavailable_real_es_is_an_error_and_closes_client(monkeypatch):
    monkeypatch.setenv("ELASTICSEARCH_URL", "http://127.0.0.1:9200")
    module = load_integration_module()
    closed = []
    error = ConnectionError("test service unavailable")

    class UnavailableClient:
        def info(self):
            raise error

        def close(self):
            closed.append(True)

    monkeypatch.setattr(
        module, "Elasticsearch", lambda *args, **kwargs: UnavailableClient()
    )
    fixture = module.real_es.__wrapped__()
    with pytest.raises(ConnectionError) as raised:
        next(fixture)
    assert raised.value is error
    assert closed == [True]
