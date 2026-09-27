import importlib
from pathlib import Path
from unittest.mock import MagicMock
import pytest

@pytest.mark.parametrize("failure", ["partial", "transport"])
def test_bulk_failures_propagate_and_close(monkeypatch, failure):
    module = importlib.import_module("evtx2es.presenters.Evtx2esPresenter")
    presenter = module.Evtx2esPresenter(Path("input"), is_quiet=True)
    state = []
    def chunks():
        try:
            yield [{"id": 1}]
            pytest.fail("continued after failed batch")
        finally:
            state.append("closed")
    monkeypatch.setattr(presenter, "evtx2es", chunks)
    client = MagicMock()
    if failure == "partial":
        client.bulk_indice.return_value = (
            0,
            [{"index": {"_id": "bad-id", "status": 400,
                        "error": {"type": "mapper_parsing_exception",
                                  "reason": "field type conflict"}}}],
        )
    else:
        client.bulk_indice.side_effect = RuntimeError("transport failed")
    monkeypatch.setattr(module, "ElasticsearchUtils", lambda **kwargs: client)
    with pytest.raises(RuntimeError) as error:
        presenter.bulk_import()
    if failure == "partial":
        assert "bad-id" in str(error.value)
        assert "field type conflict" in str(error.value)
    client.close.assert_called_once()
    assert state == ["closed"]


def test_cli_passes_tls_options(tmp_path, monkeypatch):
    module = importlib.import_module("evtx2es.views.Evtx2esView")
    source = tmp_path / "sample.evtx"
    source.write_bytes(b"regf" + b"\0" * 4096)
    client = MagicMock()
    monkeypatch.setattr(module, "Evtx2esPresenter", client)
    monkeypatch.setattr("sys.argv", ["evtx2es", str(source), "--ca-certs", "ca.pem", "--no-verify-certs"])
    module.Evtx2esView().run()
    assert client.call_args.kwargs["ca_certs"] == "ca.pem"
    assert client.call_args.kwargs["verify_certs"] is False

def test_tls_options(monkeypatch):
    module = importlib.import_module("evtx2es.models.ElasticsearchUtils")
    client = MagicMock()
    monkeypatch.setattr(module, "Elasticsearch", client)
    module.ElasticsearchUtils("localhost", 9200, "https", "user", "", ca_certs="ca.pem")
    assert client.call_args.kwargs["verify_certs"] is True
    assert client.call_args.kwargs["ca_certs"] == "ca.pem"
    assert client.call_args.kwargs["basic_auth"] == ("user", "")
