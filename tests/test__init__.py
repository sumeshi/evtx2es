# coding: utf-8
from hashlib import md5
from pathlib import Path

import pytest
from evtx2es.views.Evtx2esView import entry_point as e2e
from evtx2es.views.Evtx2jsonView import entry_point as e2j

# utils
def calc_md5(path: Path) -> str:
    if path.is_dir():
        return ''
    else:
        return md5(path.read_bytes()).hexdigest()


# command-line test cases
def test__evtx2es_help(monkeypatch):
    argv = ["evtx2es", "-h"]
    with pytest.raises(SystemExit) as exited:
        with monkeypatch.context() as m:
            m.setattr("sys.argv", argv)
            e2e()
        assert exited.value.code == 0

def test__evtx2es_version(monkeypatch):
    argv = ["evtx2es", "-v"]
    with pytest.raises(SystemExit) as exited:
        with monkeypatch.context() as m:
            m.setattr("sys.argv", argv)
            e2e()
        assert exited.value.code == 0

def test__evtx2json_help(monkeypatch):
    argv = ["evtx2json", "-h"]
    with pytest.raises(SystemExit) as exited:
        with monkeypatch.context() as m:
            m.setattr("sys.argv", argv)
            e2j()
        assert exited.value.code == 0

def test__evtx2json_version(monkeypatch):
    argv = ["evtx2json", "-v"]
    with pytest.raises(SystemExit) as exited:
        with monkeypatch.context() as m:
            m.setattr("sys.argv", argv)
            e2j()
        assert exited.value.code == 0


# behavior test cases 
def test__evtx2json_convert(monkeypatch):
    path = 'tests/cache/Security.json'
    argv = ["evtx2json", "-o", path, "tests/cache/Security.evtx"]
    with monkeypatch.context() as m:
        m.setattr("sys.argv", argv)
        e2j()
    assert calc_md5(Path(path)) == "1c99682c5f94b8d3bfaa72a5a95b360c"

def test__evtx2json_convert_multiprocessing(monkeypatch):
    path = 'tests/cache/Security-m.json'
    argv = ["evtx2json", "-o", path, "-m", "tests/cache/Security.evtx"]
    with monkeypatch.context() as m:
        m.setattr("sys.argv", argv)
        e2j()
    assert calc_md5(Path(path)) == "1c99682c5f94b8d3bfaa72a5a95b360c"
