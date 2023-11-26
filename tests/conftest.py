# config: utf-8
import hashlib
from pathlib import Path
from urllib import request

import pytest


@pytest.fixture(scope='session', autouse=True)
def prepare_eventlog():
    # setup
    ## download eventlog sample
    url = 'https://github.com/JPCERTCC/LogonTracer/raw/master/sample/Security.evtx'
    eventlog = Path(__file__).parent / Path('cache') / ('Security.evtx')
    data = request.urlopen(url).read()
    with open(eventlog.resolve(), mode="wb") as f:
        f.write(data)
    eventlog_md5 = hashlib.md5(eventlog.read_bytes()).hexdigest()
    assert eventlog_md5 == '8ba673df16853ee6d1bb6358deed35e3'

    # transition to test cases
    yield

    # teardown
    ## remove cache files
    cachedir = Path(__file__).parent / Path('cache')
    for file in cachedir.glob('**/*[!.gitkeep]'):
        file.unlink()
