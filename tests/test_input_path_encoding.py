"""Native EVTX inputs at POSIX byte paths remain serializable and distinct."""

import os
from pathlib import Path
import subprocess
import sys

import orjson
import pytest
from evtx import PyEvtxParser

from evtx2es import evtx2json
from evtx2es.models.ElasticsearchUtils import ElasticsearchUtils
from evtx2es.models.Evtx2es import format_record

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / ".github" / "status_fixture.py"
POSIX_BYTES = pytest.mark.skipif(
    os.name != "posix", reason="Non-UTF-8 filesystem byte names require POSIX"
)


def input_files(tmp_path):
    import runpy

    create_artifact = runpy.run_path(str(FIXTURE))["create_artifact"]
    raw = create_artifact(tmp_path / os.fsdecode(b"bad-\xff"))
    literal = create_artifact(tmp_path / r"bad-\udcff")
    normal = create_artifact(tmp_path / "normal")
    return raw, literal, normal


def assert_documents(documents, sources):
    assert len(documents) == 3 * 15
    raw_path = os.fsencode(sources[0].resolve()).hex()
    assert os.fsdecode(bytes.fromhex(raw_path)) == str(sources[0].resolve())
    for offset in (0, 15, 30):
        batch = documents[offset : offset + 15]
        assert [document["winlog"]["record_id"] for document in batch] == list(
            range(1, 16)
        )
        if offset == 0:
            assert all(
                document["winlog"]["source"]["file_path_bytes_hex"] == raw_path
                for document in batch
            )
    raw, literal, normal = (documents[index * 15] for index in range(3))
    assert raw["log"]["file"]["path"] == literal["log"]["file"]["path"]
    assert raw["winlog"]["source"]["file_path_bytes_hex"] == raw_path
    assert "source" not in literal["winlog"]
    assert "source" not in normal["winlog"]
    raw_record = next(PyEvtxParser(str(sources[2])).records_json())
    expected_normal = format_record(raw_record, str(sources[2]), None)
    assert normal == expected_normal
    assert ElasticsearchUtils.calc_hash(None, normal) == ElasticsearchUtils.calc_hash(
        None, expected_normal
    )
    assert raw["log"]["file"]["path"] == str(sources[0].resolve()).encode(
        "utf-8", "backslashreplace"
    ).decode("utf-8")
    assert (
        len({ElasticsearchUtils.calc_hash(None, document) for document in documents})
        == 45
    )
    assert orjson.dumps(documents)


@POSIX_BYTES
@pytest.mark.parametrize("multiprocess", [False, True])
def test_native_api_preserves_filesystem_path_bytes(
    tmp_path, monkeypatch, multiprocess
):
    from evtx2es.models.Evtx2es import Evtx2es

    sources = input_files(tmp_path)
    monkeypatch.setattr(Evtx2es, "get_cpu_count", staticmethod(lambda: 2))
    documents = [
        document
        for source in sources
        for document in evtx2json(str(source), multiprocess=multiprocess)
    ]
    assert_documents(documents, sources)


@POSIX_BYTES
@pytest.mark.parametrize("output_format", ["json", "jsonl"])
@pytest.mark.parametrize("multiprocess", [False, True])
def test_native_cli_preserves_filesystem_path_bytes(
    tmp_path, output_format, multiprocess
):
    sources = input_files(tmp_path)
    environment = {**os.environ, "PYTHON_CPU_COUNT": "2"}
    documents = []
    for index, source in enumerate(sources):
        output = tmp_path / f"records-{index}.{output_format}"
        command = [
            sys.executable,
            "-m",
            "evtx2es.views.Evtx2jsonView",
            str(source),
            "--output-file",
            str(output),
            "--format",
            output_format,
            "--quiet",
        ]
        if multiprocess:
            command.append("--multiprocess")
        result = subprocess.run(
            command, cwd=ROOT, env=environment, capture_output=True, timeout=120
        )
        assert result.returncode == 0, result.stderr.decode("utf-8", "backslashreplace")
        payload = output.read_bytes()
        documents.extend(
            orjson.loads(payload)
            if output_format == "json"
            else [orjson.loads(line) for line in payload.splitlines()]
        )
    assert_documents(documents, sources)
