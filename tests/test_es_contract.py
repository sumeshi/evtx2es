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


@pytest.mark.parametrize("quiet", [False, True])
def test_bulk_failure_closes_progress_raw_generator_then_parser(
    monkeypatch, quiet
):
    module = importlib.import_module("evtx2es.presenters.Evtx2esPresenter")
    state = []

    class Parser:
        def __init__(self, path):
            pass

        def gen_records(self, *args):
            try:
                yield [{"id": 1}]
                pytest.fail("continued after failed batch")
            finally:
                state.append("generator")

        def close(self):
            state.append("parser")

    class Progress:
        def __init__(self, records):
            self.records = records

        def __iter__(self):
            return iter(self.records)

        def close(self):
            state.append("progress")

    client = MagicMock()
    client.bulk_indice.side_effect = RuntimeError("transport failed")
    monkeypatch.setattr(module, "Evtx2es", Parser)
    monkeypatch.setattr(module, "tqdm", Progress)
    monkeypatch.setattr(module, "ElasticsearchUtils", lambda **kwargs: client)

    with pytest.raises(RuntimeError) as error:
        module.Evtx2esPresenter(Path("input"), is_quiet=quiet).bulk_import()

    assert str(error.value) == "transport failed"
    assert state.count("generator") == 1
    assert state.count("progress") == (0 if quiet else 1)
    assert state.count("parser") == 1
    assert state[-1] == "parser"
    client.close.assert_called_once()


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

def test_cli_indexes_recovered_records_continues_and_exits_partial(
    tmp_path, monkeypatch, capsys
):
    view_module = importlib.import_module("evtx2es.views.Evtx2esView")
    presenter_module = importlib.import_module("evtx2es.presenters.Evtx2esPresenter")
    paths = [tmp_path / name for name in ("good1.evtx", "partial.evtx", "good2.evtx")]
    for path in paths:
        path.write_bytes(b"fixture")
    indexed = []

    class Parser:
        def __init__(self, path):
            self.path = Path(path)
            self.diagnostics = []

        def gen_records(self, shift, multiprocess, chunk_size, tags):
            if self.path == paths[1]:
                self.diagnostics.append({
                    "source_file": str(self.path.resolve()),
                    "error": "ValueError: recoverable parser error",
                })
            yield [{"source": self.path.name}]

        def close(self):
            pass

    class Client:
        def __init__(self, **kwargs):
            pass

        def bulk_indice(self, records, index, pipeline):
            indexed.extend(records)
            return len(records), []

        def close(self):
            pass

    monkeypatch.setattr(presenter_module, "Evtx2es", Parser)
    monkeypatch.setattr(presenter_module, "ElasticsearchUtils", Client)
    monkeypatch.setattr(
        "sys.argv", ["evtx2es", "--quiet", *(str(path) for path in paths)]
    )
    with pytest.raises(SystemExit) as exited:
        view_module.Evtx2esView().run()

    captured = capsys.readouterr()
    assert exited.value.code == 1
    assert [record["source"] for record in indexed] == [path.name for path in paths]
    assert str(paths[1].resolve()) in captured.err
    assert "recoverable parser error" in captured.err
    assert captured.out == ""

def test_cli_stops_after_elasticsearch_failure(tmp_path, monkeypatch):
    view_module = importlib.import_module("evtx2es.views.Evtx2esView")
    paths = [tmp_path / name for name in ("first.evtx", "later.evtx")]
    for path in paths:
        path.write_bytes(b"fixture")
    attempted = []

    class Presenter:
        def __init__(self, input_path, **kwargs):
            self.input_path = input_path

        def bulk_import(self):
            attempted.append(self.input_path)
            raise RuntimeError("Elasticsearch unavailable")

    monkeypatch.setattr(view_module, "Evtx2esPresenter", Presenter)
    monkeypatch.setattr("sys.argv", ["evtx2es", "--quiet", *(str(p) for p in paths)])
    with pytest.raises(RuntimeError, match="Elasticsearch unavailable"):
        view_module.Evtx2esView().run()
    assert attempted == paths[:1]

def test_tls_options(monkeypatch):
    module = importlib.import_module("evtx2es.models.ElasticsearchUtils")
    client = MagicMock()
    monkeypatch.setattr(module, "Elasticsearch", client)
    module.ElasticsearchUtils("localhost", 9200, "https", "user", "", ca_certs="ca.pem")
    assert client.call_args.kwargs["verify_certs"] is True
    assert client.call_args.kwargs["ca_certs"] == "ca.pem"
    assert client.call_args.kwargs["basic_auth"] == ("user", "")
