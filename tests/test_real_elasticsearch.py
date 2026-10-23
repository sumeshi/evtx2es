"""Opt-in native ingestion tests: ELASTICSEARCH_URL=http://127.0.0.1:9200 pytest -q tests/test_real_elasticsearch.py."""

from copy import deepcopy
from hashlib import sha1
import importlib
import inspect
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tomllib
from urllib.parse import unquote, urlsplit
from uuid import uuid4

from elasticsearch import Elasticsearch
import orjson
import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["name"]


def document_id(document):
    return sha1(orjson.dumps(document, option=orjson.OPT_SORT_KEYS)).hexdigest()


@pytest.fixture(scope="module")
def real_es():
    if "ELASTICSEARCH_URL" not in os.environ:
        pytest.skip(
            "Set ELASTICSEARCH_URL to run tests against a real Elasticsearch server"
        )
    url = os.environ["ELASTICSEARCH_URL"]
    address = urlsplit(url)
    if address.scheme not in {"http", "https"} or not address.hostname:
        pytest.fail("ELASTICSEARCH_URL must be a nonempty http(s) URL")
    client = Elasticsearch(url, request_timeout=30, max_retries=0)
    indices = []
    pipelines = []
    transport = None
    try:
        # An explicitly enabled test must fail when the service is unavailable.
        info = client.info()
        expected = os.environ.get("ELASTICSEARCH_IMAGE", "elasticsearch:9.5.5").rsplit(
            ":", 1
        )[-1]
        assert info["version"]["number"] == expected
        health = client.cluster.health(wait_for_status="yellow", timeout="10s")
        assert not health["timed_out"] and health["status"] in {"yellow", "green"}
        artifact = runpy.run_path(str(ROOT / ".github" / "artifact_fixture.py"))
        cases = runpy.run_path(str(ROOT / ".github" / "elasticsearch_cases.py"))
        helper = importlib.import_module(
            f"{PACKAGE}.models.ElasticsearchUtils"
        ).ElasticsearchUtils
        transport = helper(
            address.hostname,
            address.port or (443 if address.scheme == "https" else 80),
            address.scheme,
            unquote(address.username or ""),
            unquote(address.password or ""),
        )

        def new_index(label):
            name = f"ci-{PACKAGE}-{label}-{uuid4().hex[:12]}"
            indices.append(name)
            return name

        def new_pipeline():
            name = f"ci-{PACKAGE}-{uuid4().hex[:12]}"
            pipelines.append(name)
            return name

        yield client, transport, artifact, cases, new_index, new_pipeline, address
    finally:
        try:
            for index in indices:
                client.indices.delete(index=index, ignore_unavailable=True)
            for pipeline in pipelines:
                client.options(ignore_status=404).ingest.delete_pipeline(id=pipeline)
        finally:
            if transport is not None:
                transport.close()
            client.close()


def stored_documents(client, index):
    client.indices.refresh(index=index)
    hits = client.search(index=index, size=1000, query={"match_all": {}})["hits"][
        "hits"
    ]
    assert client.count(index=index)["count"] == len(hits)
    return {hit["_id"]: hit["_source"] for hit in hits}


def test_native_api_and_cli_round_trip(real_es, tmp_path):
    client, _transport, artifact, cases, new_index, _pipeline, address = real_es
    package = importlib.import_module(PACKAGE)
    json_api = getattr(package, artifact["JSON_COMMAND"])
    es_api = getattr(package, PACKAGE)
    source = artifact["create_artifact"](tmp_path)
    api_options = artifact["API_KWARGS"]
    es_options = {
        "host": address.hostname,
        "port": address.port or (443 if address.scheme == "https" else 80),
        "scheme": address.scheme,
        "login": unquote(address.username or ""),
        "pwd": unquote(address.password or ""),
    }
    supports_multiprocessing = "multiprocess" in inspect.signature(json_api).parameters
    entry_point = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"][
        "scripts"
    ][PACKAGE]
    command_code = (
        "import importlib,sys; module,attribute=sys.argv.pop(1).split(':'); "
        "getattr(importlib.import_module(module),attribute)()"
    )
    for mode in artifact["TIMELINE_MODES"]:
        mode_options = {} if mode is None else {"timeline_mode": mode}
        documents = json_api(str(source), **api_options, **mode_options)
        assert documents
        cases["assert_native_documents"](documents, mode)
        expected = {
            document_id(document): cases["expected_source"](document)
            for document in documents
        }
        assert len(expected) == len(
            documents
        ), "Fixture must exercise distinct document IDs"
        for multiprocess in ((False, True) if supports_multiprocessing else (False,)):
            process_options = (
                {"multiprocess": multiprocess} if supports_multiprocessing else {}
            )
            for interface in ("api", "cli"):
                index = new_index(f"{interface}-{mode}-{multiprocess}".lower())
                if interface == "api":
                    es_api(
                        str(source),
                        index=index,
                        chunk_size=1,
                        **es_options,
                        **api_options,
                        **mode_options,
                        **process_options,
                    )
                else:
                    command = [
                        sys.executable,
                        "-c",
                        command_code,
                        entry_point,
                        str(source),
                        "--host",
                        es_options["host"],
                        "--port",
                        str(es_options["port"]),
                        "--scheme",
                        es_options["scheme"],
                        "--index",
                        index,
                        "--size",
                        "1",
                        "--quiet",
                        *artifact["CLI_ARGS"],
                    ]
                    if es_options["login"]:
                        command += [
                            "--login",
                            es_options["login"],
                            "--pwd",
                            es_options["pwd"],
                        ]
                    if mode is not None:
                        command += ["--timeline" if mode else "--no-timeline"]
                    if multiprocess:
                        command += ["--multiprocess"]
                    result = subprocess.run(
                        command, capture_output=True, text=True, cwd=ROOT, timeout=120
                    )
                    assert result.returncode == 0, (result.stdout, result.stderr)
                assert stored_documents(client, index) == expected


def test_bulk_reports_partial_failure_and_runs_pipeline(real_es):
    client, transport, _artifact, _cases, new_index, new_pipeline, _address = real_es
    index = new_index("partial")
    pipeline = new_pipeline()
    client.indices.create(
        index=index, mappings={"properties": {"ordinal": {"type": "long"}}}
    )
    client.ingest.put_pipeline(
        id=pipeline,
        processors=[{"set": {"field": "ci_pipeline", "value": "processed"}}],
    )
    records = [{"ordinal": 1}, {"ordinal": "not-an-integer"}, {"ordinal": 2}]
    original = deepcopy(records)
    success, failures = transport.bulk_indice(iter(records), index, pipeline)
    assert success == 2 and len(failures) == 1
    assert failures[0]["index"]["status"] == 400
    assert failures[0]["index"]["_id"] == document_id(records[1])
    assert records == original
    assert stored_documents(client, index) == {
        document_id(record): {**record, "ci_pipeline": "processed"}
        for record in (records[0], records[2])
    }


def test_artifact_evidence_and_mapping_cases(real_es):
    client, transport, _artifact, cases, new_index, _pipeline, _address = real_es
    cases["run_extra_cases"](
        client, transport, new_index, stored_documents, document_id
    )
