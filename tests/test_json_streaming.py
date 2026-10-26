"""JSON array streaming keeps byte output and atomic failure behavior."""

import importlib

import orjson
import pytest

from evtx2es.presenters.Evtx2jsonPresenter import Evtx2jsonPresenter


@pytest.mark.parametrize("quiet", [False, True])
@pytest.mark.parametrize(
    "chunks",
    [
        [],
        [[], []],
        [[{}]],
        [[], [{}], [], [{"message": "日本語\nline", "empty": []}], []],
        [
            [{"z": 1, "a": {"values": [None, True, False, 12.5, "é"]}}],
            [{"nested": [{"x": [1, 2]}, {}]}, {"empty": {}}],
        ],
    ],
)
def test_streamed_json_matches_complete_array_bytes(tmp_path, monkeypatch, chunks, quiet):
    module = importlib.import_module("evtx2es.presenters.Evtx2jsonPresenter")
    state = {"parser_closed": False}

    class Parser:
        diagnostics = []

        def __init__(self, path):
            pass

        def gen_records(self, *args):
            yield from chunks

        def close(self):
            state["parser_closed"] = True

    monkeypatch.setattr(module, "Evtx2es", Parser)
    monkeypatch.setattr(
        Evtx2jsonPresenter, "evtx2json", lambda self: pytest.fail("list API called")
    )
    output = tmp_path / "records.json"
    presenter = Evtx2jsonPresenter(tmp_path / "input.evtx", output, is_quiet=quiet)

    presenter.export_json()

    documents = [record for chunk in chunks for record in chunk]
    assert output.read_bytes() == orjson.dumps(documents, option=orjson.OPT_INDENT_2)
    assert presenter.parse_diagnostics == []
    assert state["parser_closed"]
    assert list(tmp_path.glob(".records.json.*.tmp")) == []


@pytest.mark.parametrize("quiet", [False, True])
def test_json_is_written_before_next_chunk_is_requested(tmp_path, monkeypatch, quiet):
    module = importlib.import_module("evtx2es.presenters.Evtx2jsonPresenter")
    output = tmp_path / "records.json"
    output.write_bytes(b"previous output")
    first = {"message": "日本語", "nested": {"values": [1, 2]}}
    state = {"generator_closed": False, "parser_closed": False}

    def chunks():
        try:
            yield [first]
            staged = list(tmp_path.glob(".records.json.*.tmp"))
            assert len(staged) == 1
            assert staged[0].read_bytes() == orjson.dumps(
                [first], option=orjson.OPT_INDENT_2
            )[:-2]
            assert output.read_bytes() == b"previous output"
            yield [{"next": True}]
        finally:
            state["generator_closed"] = True

    records = chunks()

    class Parser:
        diagnostics = []

        def __init__(self, path):
            pass

        def gen_records(self, *args):
            return records

        def close(self):
            state["parser_closed"] = True

    monkeypatch.setattr(module, "Evtx2es", Parser)
    Evtx2jsonPresenter(tmp_path / "input.evtx", output, is_quiet=quiet).export_json()

    assert output.read_bytes() == orjson.dumps(
        [first, {"next": True}], option=orjson.OPT_INDENT_2
    )
    assert all(state.values())


@pytest.mark.parametrize("quiet", [False, True])
@pytest.mark.parametrize("failure", ["serializer", "writer", "parser"])
def test_midstream_failure_preserves_output_and_closes_resources(
    tmp_path, monkeypatch, quiet, failure
):
    module = importlib.import_module("evtx2es.presenters.Evtx2jsonPresenter")
    output = tmp_path / "records.json"
    output.write_bytes(b"previous output")
    state = {"generator_closed": False, "parser_closed": False}

    def chunks():
        try:
            yield [{"message": "first"}]
            if failure == "parser":
                raise ValueError("parser failed")
            yield [{"message": object() if failure == "serializer" else "second"}]
            pytest.fail("consumed records after output failure")
        finally:
            state["generator_closed"] = True

    # Keep this reference to ensure cleanup does not rely on generator GC.
    records = chunks()

    class Parser:
        diagnostics = []

        def __init__(self, path):
            pass

        def gen_records(self, *args):
            return records

        def close(self):
            state["parser_closed"] = True

    monkeypatch.setattr(module, "Evtx2es", Parser)
    if failure == "writer":
        temporary_file = module.NamedTemporaryFile

        class FailingWriter:
            def __init__(self, **kwargs):
                self.file = temporary_file(**kwargs)
                self.name = self.file.name

            def __enter__(self):
                self.file.__enter__()
                return self

            def __exit__(self, *args):
                return self.file.__exit__(*args)

            def write(self, data):
                if b"second" in data:
                    raise OSError("output full")
                return self.file.write(data)

            def flush(self):
                self.file.flush()

        monkeypatch.setattr(module, "NamedTemporaryFile", FailingWriter)

    expected_error = {"serializer": TypeError, "writer": OSError, "parser": ValueError}
    with pytest.raises(expected_error[failure]):
        Evtx2jsonPresenter(tmp_path / "input.evtx", output, is_quiet=quiet).export_json()

    assert output.read_bytes() == b"previous output"
    assert list(tmp_path.glob(".records.json.*.tmp")) == []
    assert all(state.values())


def test_presenter_list_method_remains_available(tmp_path, monkeypatch):
    module = importlib.import_module("evtx2es.presenters.Evtx2jsonPresenter")
    documents = [{"n": 1}, {"n": 2}]
    state = {"parser_closed": False}

    class Parser:
        diagnostics = []

        def __init__(self, path):
            pass

        def gen_records(self, *args):
            yield documents[:1]
            yield documents[1:]

        def close(self):
            state["parser_closed"] = True

    monkeypatch.setattr(module, "Evtx2es", Parser)
    result = Evtx2jsonPresenter(
        tmp_path / "input.evtx", tmp_path / "records.json", is_quiet=True
    ).evtx2json()

    assert isinstance(result, list)
    assert result == documents
    assert state["parser_closed"]
