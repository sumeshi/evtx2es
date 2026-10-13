import importlib
import os
import sys

import pytest


def test_es_cli_imports_valid_files_once_then_fails_for_invalid_inputs(
    tmp_path, monkeypatch, capsys
):
    module = importlib.import_module("evtx2es.views.Evtx2esView")
    directory = tmp_path / "logs.evtx"
    directory.mkdir()
    nested = directory / "nested.evtx"
    nested.write_bytes(b"fixture")
    direct = tmp_path / "direct.EVTX"
    direct.write_bytes(b"fixture")
    evidence = tmp_path / "evidence.bin"
    evidence.write_bytes(b"fixture")
    accepted_link = tmp_path / "accepted.evtx"
    accepted_link.symlink_to(evidence)
    empty = tmp_path / "empty"
    empty.mkdir()
    wrong_extension = tmp_path / "wrong.txt"
    wrong_extension.write_bytes(b"not an event log")
    imported = []

    class Presenter:
        def __init__(self, input_path, **_kwargs):
            imported.append(input_path.resolve())

        def bulk_import(self):
            pass

    monkeypatch.setattr(module, "Evtx2esPresenter", Presenter)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evtx2es", "--quiet", str(direct), str(direct), str(directory),
            str(accepted_link), str(tmp_path / "missing.evtx"),
            str(wrong_extension), str(empty),
        ],
    )

    with pytest.raises(SystemExit) as exited:
        module.Evtx2esView().run()

    assert exited.value.code == 1
    assert imported == [direct.resolve(), nested.resolve(), evidence.resolve()]
    assert "skipping" in capsys.readouterr().err


@pytest.mark.skipif(
    os.name != "posix", reason="POSIX directory permissions required"
)
@pytest.mark.parametrize("mode", [0, 0o400])
def test_es_cli_reports_unreadable_subdirectory_and_keeps_readable_files(
    tmp_path, capsys, mode
):
    module = importlib.import_module("evtx2es.views.Evtx2esView")
    good = tmp_path / "good.evtx"
    good.write_bytes(b"fixture")
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    hidden = blocked / "hidden.evtx"
    hidden.write_bytes(b"fixture")
    blocked.chmod(mode)
    try:
        if os.access(blocked, os.R_OK | os.X_OK):
            pytest.skip("process can bypass chmod restrictions")
        view = object.__new__(module.Evtx2esView)
        files, had_invalid_input = view._Evtx2esView__list_evtx_files(
            [str(tmp_path)]
        )
        assert files == [good.resolve()]
        assert had_invalid_input
        error_output = capsys.readouterr().err
        assert str(blocked) in error_output or str(hidden) in error_output
        assert "no EVTX files found" not in error_output
    finally:
        blocked.chmod(0o700)

@pytest.mark.skipif(
    os.name != "posix", reason="POSIX file permissions required"
)
def test_es_cli_skips_unreadable_explicit_input_and_keeps_later_files(
    tmp_path, monkeypatch, capsys
):
    module = importlib.import_module("evtx2es.views.Evtx2esView")
    good = tmp_path / "good.evtx"
    good.write_bytes(b"fixture")
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    hidden = blocked / "hidden.evtx"
    hidden.write_bytes(b"fixture")
    good2 = tmp_path / "good2.evtx"
    good2.write_bytes(b"fixture")
    imported = []

    class Presenter:
        def __init__(self, input_path, **_kwargs):
            imported.append(input_path)

        def bulk_import(self):
            pass

    monkeypatch.setattr(module, "Evtx2esPresenter", Presenter)
    monkeypatch.setattr(
        sys,
        "argv",
        ["evtx2es", "--quiet", str(good), str(hidden), str(good2)],
    )
    blocked.chmod(0)
    try:
        if os.access(hidden, os.R_OK):
            pytest.skip("process can bypass chmod restrictions")
        with pytest.raises(SystemExit) as exited:
            module.Evtx2esView().run()

        assert exited.value.code == 1
        assert imported == [good.resolve(), good2.resolve()]
        captured = capsys.readouterr()
        assert captured.out == ""
        assert str(hidden) in captured.err
        assert "Import completed with input failures." in captured.err
    finally:
        blocked.chmod(0o700)
