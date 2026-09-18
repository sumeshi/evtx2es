"""Regression tests for standalone release license collection."""

import importlib.util
from importlib.metadata import Distribution
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_collector():
    path = ROOT / ".github" / "collect_runtime_licenses.py"
    assert path.is_file(), "Standalone releases need a license collector"
    spec = importlib.util.spec_from_file_location(
        "collect_runtime_licenses", path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_collect_installed_license_and_notice(tmp_path, monkeypatch):
    collector = load_collector()
    info = tmp_path / "example-1.0.dist-info"
    (info / "licenses").mkdir(parents=True)
    (info / "METADATA").write_text(
        "Name: example\nVersion: 1.0\n"
        "Project-URL: Source, https://example.org\n",
        encoding="utf-8",
    )
    files = {
        "licenses/COPYING.LESSER": "Example license text",
        "licenses/NOTICE": "Example copyright notice",
    }
    for name, text in files.items():
        (info / name).write_text(text, encoding="utf-8")
    (info / "RECORD").write_text(
        "".join(f"{info.name}/{name},,\n" for name in files), encoding="utf-8"
    )
    package = Distribution.at(info)
    monkeypatch.setattr(collector, "_runtime_distributions", lambda: [package])
    output = tmp_path / "bundle" / "LICENSES.txt"
    collector.collect(output)
    text = output.read_text(encoding="utf-8")
    assert (ROOT / "LICENSE").read_text(encoding="utf-8").rstrip() in text
    assert "example 1.0" in text
    assert "https://example.org" in text
    assert all(value in text for value in files.values())


@pytest.mark.parametrize(
    "filename", ["LICENSE", "LICENCE", "COPYING", "NOTICE"]
)
def test_legacy_license_paths(filename):
    collector = load_collector()
    assert collector._is_license_file(f"example-1.0.dist-info/{filename}")
    assert collector._is_license_file(f"example-1.0.dist-info\\{filename}")
    assert not collector._is_license_file("example/license.py")


def test_missing_material_blocks_output(tmp_path, monkeypatch):
    collector = load_collector()
    info = tmp_path / "example-1.0.dist-info"
    info.mkdir()
    (info / "METADATA").write_text(
        "Name: example\nVersion: 1.0\nLicense-Expression: Apache-2.0\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        collector, "_runtime_distributions", lambda: [Distribution.at(info)]
    )
    output = tmp_path / "LICENSES.txt"
    with pytest.raises(RuntimeError, match="no license file found.*example"):
        collector.collect(output)
    assert not output.exists()


def test_windows_includes_colorama(monkeypatch):
    collector = load_collector()
    names = []
    monkeypatch.setattr(collector.sys, "platform", "win32")
    monkeypatch.setattr(
        collector, "distribution", lambda name: names.append(name)
    )
    collector._runtime_distributions()
    assert "colorama" in names
    assert len(names) == len(set(names))


def test_missing_dependency_fails(monkeypatch):
    collector = load_collector()

    def missing(name):
        raise collector.PackageNotFoundError(name)

    monkeypatch.setattr(collector, "distribution", missing)
    with pytest.raises(
        RuntimeError, match="runtime dependency is not installed"
    ):
        collector._runtime_distributions()


def test_python_license_uses_build_interpreter(tmp_path, monkeypatch):
    collector = load_collector()
    monkeypatch.setattr(collector.sys, "base_prefix", str(tmp_path))
    monkeypatch.setattr(
        collector.sysconfig, "get_path", lambda name: str(tmp_path)
    )
    with pytest.raises(RuntimeError, match="Python runtime license not found"):
        collector._python_license()
    (tmp_path / "LICENSE.txt").write_text(
        "Python runtime terms", encoding="utf-8"
    )
    assert collector._python_license() == "Python runtime terms"


def test_python_license_is_in_output(tmp_path, monkeypatch):
    collector = load_collector()
    monkeypatch.setattr(collector, "_runtime_distributions", lambda: [])
    monkeypatch.setattr(
        collector, "_python_license", lambda: "Python runtime terms"
    )
    output = tmp_path / "LICENSES.txt"
    collector.collect(output)
    assert "Python runtime terms" in output.read_text(encoding="utf-8")


@pytest.mark.parametrize("upstream_text", [None, "Upstream MIT and copyright"])
def test_parser_mit_fallback(tmp_path, monkeypatch, upstream_text):
    collector = load_collector()
    info = tmp_path / "evtx-0.11.1.dist-info"
    info.mkdir()
    (info / "METADATA").write_text(
        "Name: evtx\nVersion: 0.11.1\n", encoding="utf-8"
    )
    if upstream_text:
        (info / "LICENSE").write_text(upstream_text, encoding="utf-8")
        (info / "RECORD").write_text(
            f"{info.name}/LICENSE,,\n", encoding="utf-8"
        )
    monkeypatch.setattr(
        collector, "_runtime_distributions", lambda: [Distribution.at(info)]
    )
    output = tmp_path / "LICENSES.txt"
    collector.collect(output)
    text = output.read_text(encoding="utf-8")
    fallback = (ROOT / "LICENSES/evtx-0.11.1.txt").read_text(
        encoding="utf-8"
    ).rstrip()
    if upstream_text:
        assert upstream_text in text
        assert fallback not in text
    else:
        assert fallback in text
        assert "https://opensource.org/license/mit" in text
