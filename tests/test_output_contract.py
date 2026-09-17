"""Offline output contract tests; no forensic sample download required."""
import importlib
import json
from pathlib import Path

import pytest

from evtx2es.presenters.Evtx2jsonPresenter import Evtx2jsonPresenter


@pytest.fixture(autouse=True)
def prepare_eventlog():
    """Override the legacy network fixture for these isolated unit tests."""


@pytest.mark.parametrize('output_format', ['jsonl', 'ndjson'])
@pytest.mark.parametrize('records', [[], [{'message': '日本語\nsecond line'}, {'n': 2}]])
def test_jsonl_streams_without_list_api(tmp_path, monkeypatch, output_format, records):
    module = importlib.import_module('evtx2es.presenters.Evtx2jsonPresenter')
    state = {'closed': False}
    class Parser:
        def __init__(self, path):
            pass
        def gen_records(self, *args):
            for record in records:
                yield [record]
        def close(self):
            state['closed'] = True
    monkeypatch.setattr(module, 'Evtx2es', Parser)
    monkeypatch.setattr(Evtx2jsonPresenter, 'evtx2json', lambda self: pytest.fail('list API called'))
    presenter = Evtx2jsonPresenter(str(tmp_path / 'sample.evtx'), '', is_quiet=True, output_format=output_format)
    presenter.export_json()
    assert presenter.output_path.suffix == '.jsonl'
    data = presenter.output_path.read_bytes()
    assert [json.loads(line) for line in data.splitlines()] == records
    assert data.endswith(b'\n') if records else data == b''
    assert state['closed']


def test_jsonl_writes_before_next_chunk_and_closes_on_failure(tmp_path, monkeypatch):
    module = importlib.import_module('evtx2es.presenters.Evtx2jsonPresenter')
    state = {'writes': 0, 'generator_closed': False, 'parser_closed': False}

    def chunks():
        try:
            yield [{'n': 1}]
            assert state['writes'] == 1, 'consumed next chunk before writing'
            yield [{'n': 2}]
            pytest.fail('read ahead after output failure')
        finally:
            state['generator_closed'] = True

    # Retain a reference: cleanup must not depend on garbage collection.
    records = chunks()

    class Parser:
        def __init__(self, path):
            pass
        def gen_records(self, *args):
            return records
        def close(self):
            state['parser_closed'] = True

    class Writer:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def write(self, data):
            state['writes'] += 1
            if state['writes'] == 2:
                raise OSError('output full')
            assert json.loads(data) == {'n': 1}

    monkeypatch.setattr(module, 'Evtx2es', Parser)
    monkeypatch.setattr(Path, 'open', lambda *args, **kwargs: Writer())
    presenter = Evtx2jsonPresenter(str(tmp_path / 'sample.evtx'), '', is_quiet=True, output_format='jsonl')
    with pytest.raises(OSError, match='output full'):
        presenter.export_json()
    assert state['writes'] == 2
    assert state['parser_closed']
    assert state['generator_closed']
