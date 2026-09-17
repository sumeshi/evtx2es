"""TDD tests for Evtx2esView CLI options; sample .evtx files are optional."""
import importlib
from pathlib import Path

import pytest

from evtx2es.views.Evtx2esView import Evtx2esView


def make_view(argv):
    import sys

    old = sys.argv
    sys.argv = argv
    try:
        return Evtx2esView()
    finally:
        sys.argv = old


def test_ca_certs_option_captured(monkeypatch):
    view = make_view(["evtx2es", "sample.evtx", "--ca-certs", "/path/ca.pem"])
    assert view.args.ca_certs == "/path/ca.pem"


def test_size_must_be_positive(monkeypatch):
    for bad in ["0", "-1"]:
        with pytest.raises(SystemExit) as excinfo:
            make_view(["evtx2es", "sample.evtx", "--size", bad])
        assert excinfo.value.code == 2


def test_ca_certs_passed_to_presenter(tmp_path, monkeypatch):
    fake_evtx = tmp_path / "fake.evtx"
    fake_evtx.write_bytes(b"")
    captured = {}

    class FakePresenter:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def bulk_import(self):
            pass

    module = importlib.import_module("evtx2es.views.Evtx2esView")
    monkeypatch.setattr(module, "Evtx2esPresenter", FakePresenter)
    view = make_view(["evtx2es", str(fake_evtx), "--ca-certs", str(tmp_path / "ca.pem")])
    view.run()
    assert captured["ca_certs"] == str(tmp_path / "ca.pem")
    assert captured["verify_certs"] is True
