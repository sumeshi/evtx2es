"""Compare installed Python and isolated executable output using native inputs."""

import argparse
from contextlib import contextmanager
import gzip
from hashlib import sha1, sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
from urllib.parse import unquote, urlsplit

ARTIFACT_TOKEN = "<native-artifact-path>"


def canonical_bytes(document):
    return json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def replace_path(value, old, new):
    if isinstance(value, dict):
        return {key: replace_path(item, old, new) for key, item in value.items()}
    if isinstance(value, list):
        return [replace_path(item, old, new) for item in value]
    if isinstance(value, str):
        return value.replace(old, new)
    return value


def prepare(work_dir):
    import importlib
    import inspect
    from importlib.metadata import distribution
    import runpy

    import orjson

    fixture = runpy.run_path(str(Path(__file__).with_name("artifact_fixture.py")))
    package = fixture["PACKAGE"]
    project = distribution(package)
    api = getattr(importlib.import_module(package), fixture["JSON_COMMAND"])
    es_module = importlib.import_module(f"{package}.models.ElasticsearchAdapter")
    adapter = es_module.ElasticsearchAdapter(None)
    artifact = fixture["create_artifact"](work_dir / "inputs").resolve()
    origin_directory = Path(__file__).with_name("fixtures")
    if origin_directory.is_dir():
        provenance_file = origin_directory / "provenance.json"
        provenance = json.loads(provenance_file.read_text(encoding="utf-8"))
        attribution = origin_directory / provenance["license_file"]
        if not attribution.read_bytes().strip():
            raise RuntimeError("Validation fixture attribution is empty")
        destination = work_dir / "artifact-origin"
        destination.mkdir(exist_ok=True)
        shutil.copy2(provenance_file, destination / provenance_file.name)
        shutil.copy2(attribution, destination / attribution.name)
    tag_argument = (
        "additional_tags"
        if "additional_tags" in inspect.signature(api).parameters
        else "tags"
    )
    modes = []
    for timeline in fixture["TIMELINE_MODES"]:
        kwargs = {
            **fixture["API_KWARGS"],
            "chunk_size": 1,
            tag_argument: ["binary-smoke"],
        }
        if timeline is not None:
            kwargs["timeline_mode"] = timeline
        documents = api(str(artifact), **kwargs)
        if not documents:
            raise RuntimeError("Native validation input produced no documents")
        for document in documents:
            # Verification must work with only Python's standard library.
            if canonical_bytes(document) != orjson.dumps(
                document, option=orjson.OPT_SORT_KEYS
            ):
                raise RuntimeError("Fixture requires a nonportable JSON hash encoding")
        modes.append(
            {
                "timeline": timeline,
                "documents": replace_path(documents, str(artifact), ARTIFACT_TOKEN),
                "sources": replace_path(
                    [adapter.prepare_source(record) for record in documents],
                    str(artifact),
                    ARTIFACT_TOKEN,
                ),
            }
        )
    manifest = {
        "package": package,
        "json_command": fixture["JSON_COMMAND"],
        "version": project.version,
        "entry_points": {
            entry.name: entry.value
            for entry in project.entry_points
            if entry.group == "console_scripts"
            and entry.name in (package, fixture["JSON_COMMAND"])
        },
        "input": artifact.relative_to(work_dir).as_posix(),
        "input_sha256": sha256(artifact.read_bytes()).hexdigest(),
        "cli_args": list(fixture["CLI_ARGS"]),
        "multiprocessing": fixture["SUPPORTS_MULTIPROCESSING"],
        "expected_plugins": fixture.get("EXPECTED_PLUGINS", []),
        "modes": modes,
    }
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    shutil.copyfile(__file__, work_dir / "verify.py")
    print(f"Prepared {package}: " + ", ".join(str(len(m["documents"])) for m in modes))


@contextmanager
def bulk_collector():
    """Capture real client HTTP requests; actual ES mapping is tested separately."""
    captured = []
    errors = []
    indices = {}

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_args):
            pass

        def respond(self, status, document):
            payload = canonical_bytes(document)
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("X-Elastic-Product", "Elasticsearch")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def handle_request(self):
            path = unquote(urlsplit(self.path).path)
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            if self.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
            if path.endswith("/_bulk") and self.command in ("POST", "PUT"):
                lines = raw.splitlines()
                if len(lines) % 2:
                    raise ValueError("Incomplete bulk request")
                items = []
                for offset in range(0, len(lines), 2):
                    action = json.loads(lines[offset])
                    source = json.loads(lines[offset + 1])
                    if set(action) != {"index"}:
                        raise ValueError(f"Unexpected bulk action: {action!r}")
                    metadata = action["index"]
                    captured.append((metadata, source))
                    items.append({"index": {**metadata, "status": 201}})
                self.respond(200, {"errors": False, "items": items, "took": 0})
                return
            if path == "/":
                self.respond(200, {"version": {"number": "9.5.5"}})
                return
            parts = path.strip("/").split("/")
            if len(parts) == 1 and self.command == "GET":
                index = parts[0]
                if index in indices:
                    self.respond(
                        200, {index: {"aliases": {}, "mappings": indices[index]}}
                    )
                else:
                    self.respond(
                        404,
                        {"error": {"type": "index_not_found_exception"}, "status": 404},
                    )
                return
            if len(parts) == 1 and self.command == "PUT":
                body = json.loads(raw) if raw else {}
                indices[parts[0]] = body.get("mappings", {})
                self.respond(200, {"acknowledged": True, "index": parts[0]})
                return
            if len(parts) == 2 and parts[1] == "_mapping" and self.command == "PUT":
                indices.setdefault(parts[0], {}).update(json.loads(raw))
                self.respond(200, {"acknowledged": True})
                return
            raise ValueError(f"Unexpected HTTP request: {self.command} {path}")

        def do_GET(self):
            try:
                self.handle_request()
            except Exception as error:
                errors.append(str(error))
                self.respond(500, {"error": str(error), "status": 500})

        do_POST = do_PUT = do_GET

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield server.server_port, captured, errors
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=10)


def command_prefix(name, manifest, binary_dir, source):
    if source:
        code = (
            "import importlib,sys; "
            "module,entry=sys.argv.pop(1).split(':'); "
            "getattr(importlib.import_module(module),entry)()"
        )
        return [sys.executable, "-c", code, manifest["entry_points"][name]]
    suffix = ".exe" if os.name == "nt" else ""
    executable = (binary_dir / (name + suffix)).resolve()
    if not executable.is_file():
        raise RuntimeError(f"Missing executable: {executable}")
    return [str(executable)]


def verify(work_dir, binary_dir, source=False):
    manifest = json.loads((work_dir / "manifest.json").read_text(encoding="utf-8"))
    artifact = (work_dir / manifest["input"]).resolve()
    if sha256(artifact.read_bytes()).hexdigest() != manifest["input_sha256"]:
        raise RuntimeError("Validation artifact checksum mismatch")
    cwd = work_dir / "execution"
    cwd.mkdir(exist_ok=True)
    outputs = work_dir / "outputs"
    outputs.mkdir(exist_ok=True)
    logs = work_dir / "logs"
    logs.mkdir(exist_ok=True)
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in ("PYTHONPATH", "PYTHONHOME")
    }
    environment.update(PYTHON_CPU_COUNT="2", PYTHONNOUSERSITE="1", PYTHONUTF8="1")
    summary = {
        "package": manifest["package"],
        "source_commands": source,
        "python": sys.version,
        "cases": [],
        "es_transport": "stdlib HTTP collector; actual ES is a separate CI job",
    }

    def run(label, command):
        result = subprocess.run(
            command,
            cwd=cwd,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
        )
        (logs / (label + ".stdout")).write_text(result.stdout, encoding="utf-8")
        (logs / (label + ".stderr")).write_text(result.stderr, encoding="utf-8")
        if result.returncode or result.stderr:
            raise RuntimeError(
                f"{label}: exit {result.returncode}; stderr: {result.stderr}"
            )
        return result

    prefixes = {
        name: command_prefix(name, manifest, binary_dir, source)
        for name in (manifest["package"], manifest["json_command"])
    }
    try:
        for name, prefix in prefixes.items():
            help_text = run(name + "-help", [*prefix, "--help"]).stdout
            version = run(name + "-version", [*prefix, "--version"]).stdout.strip()
            if version != manifest["version"]:
                raise RuntimeError(f"{name}: incorrect version {version!r}")
            if any(mode["timeline"] is not None for mode in manifest["modes"]):
                if "--no-timeline" not in help_text:
                    raise RuntimeError(f"{name}: missing --no-timeline option")
            if manifest["expected_plugins"]:
                inventory = run(name + "-plugins", [*prefix, "--list-plugins"]).stdout
                for plugin in manifest["expected_plugins"]:
                    if not any(
                        line.startswith(plugin + ":") for line in inventory.splitlines()
                    ):
                        raise RuntimeError(f"{name}: plugin {plugin!r} missing")

        with bulk_collector() as (port, captured, errors):
            for mode in manifest["modes"]:
                timeline = mode["timeline"]
                variants = [("default", [])]
                if timeline is False:
                    variants = [("standard", ["--no-timeline"])]
                elif timeline is True:
                    variants = [
                        ("timeline-default", []),
                        ("timeline-explicit", ["--timeline"]),
                    ]
                expected = replace_path(
                    mode["documents"], ARTIFACT_TOKEN, str(artifact)
                )
                expected_sources = replace_path(
                    mode["sources"], ARTIFACT_TOKEN, str(artifact)
                )
                processes = (False, True) if manifest["multiprocessing"] else (False,)
                for variant, flags in variants:
                    for multiprocess in processes:
                        label = (
                            f"{variant}-{'multiprocess' if multiprocess else 'serial'}"
                        )
                        arguments = [
                            str(artifact),
                            "--quiet",
                            "--size",
                            "1",
                            "--tags",
                            "binary-smoke",
                            *manifest["cli_args"],
                            *flags,
                        ]
                        if multiprocess:
                            arguments.append("--multiprocess")
                        for output_format in ("json", "jsonl"):
                            case = label + "-" + output_format
                            destination = outputs / (case + "." + output_format)
                            run(
                                case,
                                [
                                    *prefixes[manifest["json_command"]],
                                    *arguments,
                                    "--format",
                                    output_format,
                                    "-o",
                                    str(destination),
                                ],
                            )
                            content = destination.read_text(encoding="utf-8")
                            actual = (
                                json.loads(content)
                                if output_format == "json"
                                else [json.loads(line) for line in content.splitlines()]
                            )
                            if actual != expected:
                                raise RuntimeError(
                                    f"{case}: native document/order mismatch"
                                )
                            summary["cases"].append(
                                {"case": case, "documents": len(actual)}
                            )
                            print("Passed", case, len(actual), flush=True)
                        case = label + "-elasticsearch"
                        index = "binary-smoke-" + label
                        start = len(captured)
                        run(
                            case,
                            [
                                *prefixes[manifest["package"]],
                                *arguments,
                                "--host",
                                "127.0.0.1",
                                "--port",
                                str(port),
                                "--scheme",
                                "http",
                                "--index",
                                index,
                            ],
                        )
                        actual_bulk = captured[start:]
                        expected_bulk = [
                            (
                                {
                                    "_index": index,
                                    "_id": sha1(canonical_bytes(record)).hexdigest(),
                                },
                                source_record,
                            )
                            for record, source_record in zip(expected, expected_sources)
                        ]
                        if errors or actual_bulk != expected_bulk:
                            raise RuntimeError(
                                f"{case}: ES source/ID/order mismatch; {errors}"
                            )
                        summary["cases"].append(
                            {"case": case, "documents": len(actual_bulk)}
                        )
                        print("Passed", case, len(actual_bulk), flush=True)
    finally:
        (work_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "verify"))
    parser.add_argument("--work-dir", type=Path, default=Path("dist/validation"))
    parser.add_argument("--binary-dir", type=Path, default=Path("dist"))
    parser.add_argument(
        "--source", action="store_true", help="Validate installed console entry points."
    )
    args = parser.parse_args()
    work_dir = args.work_dir.resolve()
    if args.operation == "prepare":
        prepare(work_dir)
    else:
        verify(work_dir, args.binary_dir.resolve(), args.source)


if __name__ == "__main__":
    main()
