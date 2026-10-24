"""Build the declared console entry points with the same Nuitka configuration."""

import argparse
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tomllib


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("dist"))
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument(
        "--command", action="append", help="Build only selected declared commands."
    )
    args = parser.parse_args()
    if args.jobs <= 0:
        parser.error("--jobs must be greater than zero")
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    copies = output_dir / "validation" / "binaries"
    copies.mkdir(parents=True, exist_ok=True)
    suffix = ".exe" if os.name == "nt" else ""
    selected = args.command or list(project["scripts"])
    if any(command not in project["scripts"] for command in selected):
        parser.error("--command must name a declared console script")
    for command in selected:
        entry_point = project["scripts"][command]
        module, function = entry_point.split(":")
        if function != "entry_point":
            raise RuntimeError(f"Unsupported executable entry point: {entry_point}")
        source = root / "src" / (module.replace(".", "/") + ".py")
        if not source.is_file():
            raise RuntimeError(f"Missing executable source: {source}")
        executable = command + suffix
        subprocess.run(
            [
                sys.executable,
                "-m",
                "nuitka",
                *shlex.split(os.environ.get("NUITKA_EXTRA_ARGS", "")),
                "--standalone",
                "--onefile",
                "--follow-imports",
                f"--include-distribution-metadata={project['name']}",
                "--enable-plugin=multiprocessing",
                "--no-deployment-flag=self-execution",
                f"--jobs={args.jobs}",
                "-o",
                executable,
                f"--output-dir={output_dir}",
                "--assume-yes-for-downloads",
                str(source),
            ],
            cwd=root,
            check=True,
        )
        shutil.copy2(output_dir / executable, copies / executable)
    license_file = output_dir / "LICENSES.txt"
    if license_file.is_file():
        shutil.copy2(license_file, copies.parent / license_file.name)
    sources = output_dir / "sources"
    if sources.is_dir():
        shutil.copytree(sources, copies.parent / "sources", dirs_exist_ok=True)


if __name__ == "__main__":
    main()
