import sys

from evtx2es.views.Evtx2jsonView import entry_point

import pytest


def test_help():
    sys.argv = [sys.argv[0], "-h"]
    with pytest.raises(SystemExit) as exited:
        entry_point()
    assert exited.value.code == 0


def test_convert_to_json():
    sys.argv = [sys.argv[0], "Security.evtx"]
    assert entry_point() is None


def test_convert_to_json_with_multiprocess():
    sys.argv = [sys.argv[0], "Security.evtx", "-m"]
    assert entry_point() is None
