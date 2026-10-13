"""Offline output contract tests; no forensic sample download required."""
import importlib
import json
import os
import stat
import pytest

from evtx2es.presenters.Evtx2jsonPresenter import Evtx2jsonPresenter


@pytest.mark.parametrize('output_format', ['jsonl', 'ndjson'])
@pytest.mark.parametrize('records', [[], [{'message': '日本語\nsecond line'}, {'n': 2}]])
def test_jsonl_streams_without_list_api(tmp_path, monkeypatch, output_format, records):
    module = importlib.import_module('evtx2es.presenters.Evtx2jsonPresenter')
    state = {'closed': False}
    class Parser:
        def __init__(self, path):
            self.diagnostics = []
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
            self.diagnostics = []
        def gen_records(self, *args):
            return records
        def close(self):
            state['parser_closed'] = True

    class Writer:
        name = None

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
    def fail_temp_file(**kwargs):
        temp_path = tmp_path / f"{kwargs['prefix']}test{kwargs['suffix']}"
        temp_path.touch()
        writer = Writer()
        writer.name = str(temp_path)
        return writer

    monkeypatch.setattr(module, 'NamedTemporaryFile', fail_temp_file)
    presenter = Evtx2jsonPresenter(str(tmp_path / 'sample.evtx'), '', is_quiet=True, output_format='jsonl')
    with pytest.raises(OSError, match='output full'):
        presenter.export_json()
    assert state['writes'] == 2
    assert state['parser_closed']
    assert state['generator_closed']

@pytest.mark.parametrize('output_format', ['json', 'jsonl'])
@pytest.mark.parametrize('scenario', ['recovered', 'empty_partial'])
def test_quiet_cli_publishes_recovered_records_before_partial_exit(
    tmp_path, monkeypatch, capsys, output_format, scenario
):
    view_module = importlib.import_module('evtx2es.views.Evtx2jsonView')
    model_module = importlib.import_module('evtx2es.models.Evtx2es')
    source = tmp_path / 'input.evtx'
    output = tmp_path / ('output.json' if output_format == 'json' else 'output.jsonl')
    source.write_bytes(b'fixture')
    if scenario == 'empty_partial':
        output.write_bytes(b'previous output')

    class RecoveringIterator:
        def __init__(self):
            items = (
                [ValueError('damaged record')]
                if scenario == 'empty_partial'
                else [{'n': 1}, ValueError('damaged record'), {'n': 2}]
            )
            self.items = iter(items)

        def __iter__(self):
            return self

        def __next__(self):
            item = next(self.items)
            if isinstance(item, Exception):
                raise item
            return item

    class Parser:
        def __init__(self, file_object):
            pass

        def records_json(self):
            return RecoveringIterator()

    monkeypatch.setattr(model_module, 'PyEvtxParser', Parser)
    monkeypatch.setattr(
        model_module, 'process_by_chunk', lambda records, *args: list(records)
    )
    monkeypatch.setattr(
        'sys.argv',
        ['evtx2json', '--quiet', '--format', output_format,
         str(source), '--output-file', str(output)],
    )
    with pytest.raises(SystemExit) as exited:
        view_module.Evtx2jsonView().run()

    captured = capsys.readouterr()
    assert exited.value.code == 1
    assert captured.out == ''
    assert str(source.resolve()) in captured.err
    assert 'damaged record' in captured.err
    if scenario == 'empty_partial':
        assert output.read_bytes() == b'previous output'
    else:
        records = (
            json.loads(output.read_text())
            if output_format == 'json'
            else [json.loads(line) for line in output.read_text().splitlines()]
        )
        assert records == [{'n': 1}, {'n': 2}]
    assert list(tmp_path.glob(f'.{output.name}.*.tmp')) == []

@pytest.mark.parametrize('output_format', ['json', 'jsonl'])
def test_quiet_cli_failure_preserves_existing_output_and_cleans_temp_file(
    tmp_path, monkeypatch, capsys, output_format
):
    view_module = importlib.import_module('evtx2es.views.Evtx2jsonView')
    presenter_module = importlib.import_module('evtx2es.presenters.Evtx2jsonPresenter')
    source = tmp_path / 'input.evtx'
    output = tmp_path / 'output.json'
    source.write_bytes(b'fixture')
    output.write_bytes(b'previous output')

    class Parser:
        def __init__(self, path):
            self.diagnostics = []
        def gen_records(self, *args):
            yield [{'n': 1}]
            raise ValueError('parser broke')
        def close(self):
            pass

    monkeypatch.setattr(presenter_module, 'Evtx2es', Parser)
    monkeypatch.setattr(
        'sys.argv',
        ['evtx2json', '--quiet', '--format', output_format,
         str(source), '--output-file', str(output)],
    )
    with pytest.raises(SystemExit) as exited:
        view_module.Evtx2jsonView().run()

    captured = capsys.readouterr()
    assert exited.value.code == 1
    assert captured.out == ''
    assert 'parser broke' in captured.err
    assert 'completed successfully' not in captured.out + captured.err
    assert output.read_bytes() == b'previous output'
    assert list(tmp_path.glob(f'.{output.name}.*.tmp')) == []


@pytest.mark.skipif(os.name != "posix", reason="POSIX file modes only")
@pytest.mark.parametrize("output_format", ["json", "jsonl"])
def test_export_preserves_existing_output_mode(
    tmp_path, monkeypatch, output_format
):
    module = importlib.import_module("evtx2es.presenters.Evtx2jsonPresenter")
    source = tmp_path / "input.evtx"
    output = tmp_path / "output.json"
    source.write_bytes(b"fixture")
    output.write_bytes(b"previous")
    output.chmod(0o664)

    class Parser:
        def __init__(self, path):
            self.diagnostics = []

        def gen_records(self, *args):
            yield [{"record": 1}]

        def close(self):
            pass

    monkeypatch.setattr(module, "Evtx2es", Parser)
    Evtx2jsonPresenter(
        source, output, is_quiet=True, output_format=output_format
    ).export_json()

    assert stat.S_IMODE(output.stat().st_mode) == 0o664
