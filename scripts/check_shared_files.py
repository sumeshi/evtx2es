"""Check mirrored files in the four sibling repository checkouts."""

import argparse
from pathlib import Path
import subprocess
import sys
import tomllib

REPOSITORIES = ("evtx2es", "mft2es", "prefetch2es", "reg2es")
SHARED_FILES = (
    "src/{package}/models/ElasticsearchUtils.py",
    "src/{package}/views/BaseView.py",
    ".github/collect_runtime_licenses.py",
    ".github/binary_smoke.py",
    ".github/build_binaries.py",
    ".github/report_pytest.py",
    ".github/workflows/test-elasticsearch.yaml",
    ".devcontainer/Dockerfile",
    ".devcontainer/devcontainer.json",
    ".devcontainer/postCreateCommands.fish",
    "tests/test_elasticsearch_utils.py",
    "tests/test_license_collection_contract.py",
    "tests/test_common_cli.py",
    "tests/test_real_elasticsearch.py",
    "tests/test_real_elasticsearch_configuration.py",
    "scripts/check_shared_files.py",
)
MP_FILES = (
    "src/{package}/models/MultiprocessingUtils.py",
    "tests/test_multiprocessing_contract.py",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Parent directory containing all four repository checkouts.",
    )
    args = parser.parse_args()
    missing = [name for name in REPOSITORIES if not (args.root / name).is_dir()]
    if missing:
        parser.error("Missing sibling repositories: " + ", ".join(missing))
    failures = []
    common_names = ("elasticsearch", "orjson", "tqdm", "urllib3")
    reference_dependencies = None
    reference_tools = None
    for package in REPOSITORIES:
        project = tomllib.loads((args.root / package / "pyproject.toml").read_text())
        dependencies = [
            item
            for item in project["project"]["dependencies"]
            if item.startswith(common_names)
        ]
        tools = project["dependency-groups"]["dev"]
        if reference_dependencies is None:
            reference_dependencies, reference_tools = dependencies, tools
        else:
            if dependencies != reference_dependencies:
                failures.append(f"Common dependency constraints differ: {package}")
            if tools != reference_tools:
                failures.append(f"Development tool constraints differ: {package}")
    for package in REPOSITORIES:
        repository = args.root / package
        for relative in (
            ".github/license_manifest.json",
            ".github/artifact_fixture.py",
            ".github/elasticsearch_cases.py",
        ):
            path = repository / relative
            if not path.is_file():
                failures.append(f"Missing artifact configuration: {path}")
        for relative in (
            ".github/license_manifest.json",
            ".github/shared-config.json",
            ".flake8",
        ):
            ignored = subprocess.run(
                ["git", "check-ignore", "--quiet", "--no-index", "--", relative],
                cwd=repository,
                capture_output=True,
            )
            if ignored.returncode == 0:
                failures.append(
                    f"Development configuration is gitignored: {repository / relative}"
                )
            elif ignored.returncode != 1:
                failures.append(f"Unable to check gitignore: {repository / relative}")

    def compare(template, repositories, normalize_package=False):
        reference = None
        for package in repositories:
            path = args.root / package / template.format(package=package)
            if not path.is_file():
                failures.append(f"Missing file: {path}")
                continue
            contents = path.read_bytes()
            if normalize_package:
                contents = contents.replace(package.encode(), b"artifact")
            if reference is None:
                reference = contents
            elif contents != reference:
                failures.append(f"Shared file differs: {path}")

    for template in SHARED_FILES:
        compare(template, REPOSITORIES)
    for template in MP_FILES:
        compare(template, REPOSITORIES[:3])
    compare("src/{package}/models/ElasticsearchAdapter.py", ("evtx2es", "prefetch2es"))
    compare("src/{package}/views/ArtifactOptions.py", ("mft2es", "prefetch2es"))
    compare(".devcontainer/docker-compose.yaml", REPOSITORIES, normalize_package=True)
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print("Shared files match across all four repositories.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
