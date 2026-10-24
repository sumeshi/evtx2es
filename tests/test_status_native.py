"""Exercise mixed Status values through the real native parser, API and CLI."""

from hashlib import sha256
import json
import os
from pathlib import Path
import runpy
import struct
import subprocess
import sys
import zlib

from evtx import PyEvtxParser
import orjson
import pytest

from evtx2es import evtx2json
from evtx2es.models.Evtx2es import Evtx2es

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = runpy.run_path(str(ROOT / ".github" / "status_fixture.py"))
STATUSES = FIXTURE["STATUSES"]


def assert_status_documents(documents):
    assert len(documents) == len(STATUSES)
    assert [doc["winlog"]["record_id"] for doc in documents] == list(
        range(1, len(STATUSES) + 1)
    )
    for document, status in zip(documents, STATUSES):
        winlog = document["winlog"]
        expected = (
            status
            if isinstance(status, str)
            else json.dumps(
                status, sort_keys=True, ensure_ascii=False, separators=(",", ":")
            )
        )
        assert winlog["event_data"]["Status"] == expected
        assert type(winlog["event_data"]["Status"]) is str
        restored = json.loads(winlog["event_data_original"]["Status"])
        assert restored == status and type(restored) is type(status)


def test_synthetic_fixture_checksums_and_native_status_types(tmp_path):
    source = FIXTURE["create_artifact"](tmp_path)
    payload = source.read_bytes()
    chunk = payload[4096:]
    assert len(payload) == 4096 + 65536
    assert struct.unpack_from("<I", payload, 124)[0] == zlib.crc32(payload[:120])
    assert struct.unpack_from("<I", chunk, 124)[0] == zlib.crc32(
        chunk[:120] + chunk[128:512]
    )
    end = struct.unpack_from("<I", chunk, 48)[0]
    assert struct.unpack_from("<I", chunk, 52)[0] == zlib.crc32(chunk[512:end])
    records = list(PyEvtxParser(str(source)).records_json())
    assert len(records) == len(STATUSES)
    for record, expected in zip(records, STATUSES):
        status = orjson.loads(record["data"])["Event"]["EventData"]["Status"]
        assert status == expected and type(status) is type(expected)
    assert source.read_bytes() == payload


@pytest.mark.parametrize("multiprocess", [False, True])
@pytest.mark.parametrize("chunk_size", [1, 500])
def test_native_status_api_preserves_search_values_and_typed_originals(
    tmp_path, monkeypatch, multiprocess, chunk_size
):
    source = FIXTURE["create_artifact"](tmp_path)
    before = sha256(source.read_bytes()).digest()
    monkeypatch.setattr(Evtx2es, "get_cpu_count", staticmethod(lambda: 2))

    documents = evtx2json(str(source), multiprocess=multiprocess, chunk_size=chunk_size)

    assert_status_documents(documents)
    assert sha256(source.read_bytes()).digest() == before


@pytest.mark.parametrize("output_format", ["json", "jsonl"])
@pytest.mark.parametrize("multiprocess", [False, True])
@pytest.mark.parametrize("chunk_size", [1, 500])
def test_native_status_cli_preserves_search_values_and_typed_originals(
    tmp_path, output_format, multiprocess, chunk_size
):
    source = FIXTURE["create_artifact"](tmp_path)
    before = sha256(source.read_bytes()).digest()
    destination = tmp_path / f"status.{output_format}"
    command = [
        sys.executable,
        "-c",
        "from evtx2es.views.Evtx2jsonView import entry_point; entry_point()",
        str(source),
        "--output-file",
        str(destination),
        "--format",
        output_format,
        "--size",
        str(chunk_size),
        "--quiet",
    ]
    if multiprocess:
        command.append("--multiprocess")
    environment = {**os.environ, "PYTHON_CPU_COUNT": "2"}

    result = subprocess.run(
        command, cwd=ROOT, env=environment, capture_output=True, text=True, timeout=120
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    payload = destination.read_bytes()
    documents = (
        orjson.loads(payload)
        if output_format == "json"
        else [orjson.loads(line) for line in payload.splitlines()]
    )
    assert_status_documents(documents)
    assert sha256(source.read_bytes()).digest() == before
