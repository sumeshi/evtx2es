"""Release notices must remain complete when installed metadata is incomplete."""

import importlib.util
from importlib.metadata import Distribution
from pathlib import Path

import pytest


def collector_with_package(tmp_path, monkeypatch, version="1.0", license_text=None):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "license_collection_contract", root / ".github/collect_runtime_licenses.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    info = tmp_path / f"example-{version}.dist-info"
    info.mkdir()
    (info / "METADATA").write_text(
        f"Name: example\nVersion: {version}\n", encoding="utf-8"
    )
    if license_text is not None:
        (info / "LICENSE").write_text(license_text, encoding="utf-8")
        (info / "RECORD").write_text(f"{info.name}/LICENSE,,\n", encoding="utf-8")
    monkeypatch.setattr(
        module, "_runtime_distributions", lambda: [Distribution.at(info)]
    )
    return module


def test_blank_installed_license_preserves_existing_output(tmp_path, monkeypatch):
    collector = collector_with_package(tmp_path, monkeypatch, license_text=" \n\t")
    output = tmp_path / "LICENSES.txt"
    output.write_text("Previous complete notices", encoding="utf-8")

    with pytest.raises(RuntimeError, match="no license file found.*example"):
        collector.collect(output)

    assert output.read_text(encoding="utf-8") == "Previous complete notices"


@pytest.mark.parametrize("version", ["1.0", "2.0"])
def test_verified_fallback_applies_only_to_its_exact_version(
    tmp_path, monkeypatch, version
):
    collector = collector_with_package(tmp_path, monkeypatch, version)
    monkeypatch.setitem(
        collector.MANIFEST,
        "fallbacks",
        [
            {
                "distribution": "example",
                "version": "1.0",
                "text": "Verified vendor terms",
            }
        ],
    )
    output = tmp_path / "LICENSES.txt"

    if version == "1.0":
        collector.collect(output)
        assert "Verified vendor terms" in output.read_text(encoding="utf-8")
    else:
        with pytest.raises(RuntimeError, match="no license file found.*example"):
            collector.collect(output)
        assert not output.exists()


@pytest.mark.parametrize("source", ["text", "path"])
def test_blank_fallback_cannot_replace_missing_license(tmp_path, monkeypatch, source):
    collector = collector_with_package(tmp_path, monkeypatch)
    fallback = {"distribution": "example", "version": "1.0"}
    if source == "path":
        material = tmp_path / "vendor-license.txt"
        material.write_text(" \n\t", encoding="utf-8")
        fallback["path"] = str(material)
    else:
        fallback["text"] = " \n\t"
    monkeypatch.setitem(collector.MANIFEST, "fallbacks", [fallback])
    output = tmp_path / "LICENSES.txt"

    with pytest.raises(RuntimeError, match="empty license material"):
        collector.collect(output)

    assert not output.exists()
