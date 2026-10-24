"""Collect installed dependency notices for standalone release archives.

Run in the same environment as Nuitka. Missing material stops the release;
license identifiers and links are not substitutes for license text.
Artifact-specific dependencies and notices are in license_manifest.json.
"""

from __future__ import annotations

import argparse
from importlib.metadata import PackageNotFoundError, distribution
import json
from pathlib import Path
import sys
import sysconfig

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads(
    Path(__file__).with_name("license_manifest.json").read_text(encoding="utf-8")
)
STANDALONE_DISTRIBUTIONS = tuple(MANIFEST["standalone_distributions"])


def _is_license_file(path: str) -> bool:
    normalized = path.replace("\\", "/").lower()
    filename = normalized.rsplit("/", 1)[-1]
    return ".dist-info/licenses/" in normalized or (
        ".dist-info/" in normalized
        and filename.startswith(("license", "licence", "notice", "copying"))
    )


def _runtime_distributions():
    names = STANDALONE_DISTRIBUTIONS
    if sys.platform == "win32":
        names += ("colorama",)
    packages = []
    for name in names:
        try:
            packages.append(distribution(name))
        except PackageNotFoundError as exc:
            raise RuntimeError(f"runtime dependency is not installed: {name}") from exc
    return packages


def _project_url(metadata) -> str:
    for entry in metadata.get_all("Project-URL") or []:
        label, separator, url = entry.partition(",")
        if separator and label.strip().lower() in {
            "source",
            "source code",
            "repository",
            "homepage",
        }:
            return url.strip()
    return metadata.get("Home-page") or "Not specified"


def _python_license() -> str:
    # Read the bundled interpreter license, never the project license.
    for directory in (
        Path(sys.base_prefix),
        Path(sysconfig.get_path("stdlib")),
    ):
        for filename in ("LICENSE.txt", "LICENSE"):
            path = directory / filename
            if path.is_file():
                text = path.read_text(encoding="utf-8")
                if text.strip():
                    return text
    raise RuntimeError("Python runtime license not found in the build interpreter")


def _manifest_text(entry: dict) -> str:
    text = (
        entry["text"]
        if "text" in entry
        else (PROJECT_ROOT / entry["path"]).read_text(encoding="utf-8")
    )
    if not text.strip():
        raise RuntimeError(
            f"empty license material: {entry.get('path', entry.get('distribution', 'notice'))}"
        )
    return text


def collect(output_file: Path) -> None:
    sections = ["License and Third-Party Notices", *MANIFEST["notices"]]

    def append_text(title: str, text: str) -> None:
        sections.append(f"{title}\n{'=' * len(title)}\n\n{text.rstrip()}")

    append_text(
        f"{MANIFEST['project_name']} — MIT", _manifest_text({"path": "LICENSE"})
    )
    for entry in MANIFEST["license_files"]:
        append_text(entry["title"], _manifest_text(entry))
    append_text(f"Python {sys.version.split()[0]}", _python_license())

    for package in _runtime_distributions():
        metadata = package.metadata
        name = metadata.get("Name", package.name)
        materials = []
        for path in sorted(package.files or [], key=str):
            if _is_license_file(str(path)):
                text = Path(package.locate_file(path)).read_text(encoding="utf-8")
                if text.strip():
                    materials.append(f"--- {path} ---\n{text.rstrip()}")
        if not materials:
            for fallback in MANIFEST["fallbacks"]:
                if (name, package.version) == (
                    fallback["distribution"],
                    fallback["version"],
                ):
                    materials.append(_manifest_text(fallback))
                    break
        if not materials:
            raise RuntimeError(
                f"no license file found for runtime dependency: "
                f"{name} {package.version}; "
                "obtain verified upstream license and copyright notices "
                "before releasing"
            )
        append_text(
            f"{name} {package.version}",
            f"Project: {_project_url(metadata)}\n\n" + "\n\n".join(materials),
        )

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text("\n\n".join(sections) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_file", type=Path)
    collect(parser.parse_args().output_file)


if __name__ == "__main__":
    main()
