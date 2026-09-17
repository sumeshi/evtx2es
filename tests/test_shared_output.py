"""Shared output validation and CLI contract."""
import importlib
import pytest
from evtx2es.presenters.Evtx2jsonPresenter import Evtx2jsonPresenter

@pytest.mark.parametrize("output_format", ["json", "jsonl", "ndjson"])
@pytest.mark.parametrize("alias", ["same", "symlink", "hardlink"])
def test_output_preserves_input(tmp_path, output_format, alias):
    source = tmp_path / "input"
    source.write_bytes(b"evidence")
    destination = source
    if alias != "same":
        destination = tmp_path / "alias"
        if alias == "symlink":
            destination.symlink_to(source)
        else:
            destination.hardlink_to(source)
    with pytest.raises(ValueError):
        Evtx2jsonPresenter(source, str(destination), output_format=output_format).export_json()
    assert source.read_bytes() == b"evidence"


@pytest.mark.parametrize("command", ["Evtx2json", "Evtx2es"])
@pytest.mark.parametrize("size", ["0", "-1"])
def test_cli_rejects_nonpositive_size(monkeypatch, command, size):
    module = importlib.import_module(f"evtx2es.views.{command}View")
    monkeypatch.setattr("sys.argv", [command.lower(), "input", "--size", size])
    with pytest.raises(SystemExit) as exited:
        getattr(module, command + "View")()
    assert exited.value.code == 2

def test_invalid_format_rejected(tmp_path):
    with pytest.raises(ValueError):
        Evtx2jsonPresenter(tmp_path / "input", "", output_format="csv")

@pytest.mark.parametrize("output_format", ["jsonl", "ndjson"])
def test_cli_accepts_format(monkeypatch, output_format):
    module = importlib.import_module("evtx2es.views.Evtx2jsonView")
    monkeypatch.setattr("sys.argv", ["evtx2json", "input", "--format", output_format])
    view = module.Evtx2jsonView()
    assert view.args.format == output_format
