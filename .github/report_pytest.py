"""Emit bounded GitHub annotations from pytest JUnit failure entries."""

import argparse
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

MAX_ANNOTATIONS = 20
MAX_TITLE = 200
MAX_IDENTIFIER = 800
MAX_MESSAGE = 1500
MAX_TRACEBACK = 8000


def truncate(text, limit):
    if len(text) <= limit:
        return text
    marker = "\n... (truncated) ...\n"
    start = (limit - len(marker)) // 2
    end = limit - len(marker) - start
    return text[:start] + marker + text[-end:]


def escape_data(text):
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def annotation(level, title, text):
    title = (
        escape_data(truncate(title, MAX_TITLE)).replace(":", "%3A").replace(",", "%2C")
    )
    print(f"::{level} title={title}::{escape_data(text)}", flush=True)


def report(path):
    if not path.is_file():
        annotation(
            "notice",
            "pytest JUnit",
            "JUnit report is missing; no failure annotations emitted.",
        )
        return
    try:
        root = ET.fromstring(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ET.ParseError) as error:
        annotation(
            "notice",
            "pytest JUnit",
            f"JUnit report could not be read ({type(error).__name__}).",
        )
        return
    failures = 0
    for case in root.iter():
        if case.tag.rsplit("}", 1)[-1] != "testcase":
            continue
        identifier = (
            "::".join(
                part
                for part in (case.get("classname", ""), case.get("name", ""))
                if part
            )
            or "<unnamed test>"
        )
        for error in case:
            kind = error.tag.rsplit("}", 1)[-1]
            if kind not in ("failure", "error"):
                continue
            failures += 1
            if failures > MAX_ANNOTATIONS:
                continue
            details = (
                f"test: {truncate(identifier, MAX_IDENTIFIER)}\n"
                f"type: {truncate(error.get('type', kind), MAX_TITLE)}\n"
                f"message: {truncate(error.get('message', ''), MAX_MESSAGE)}\n"
                f"traceback:\n{truncate(''.join(error.itertext()).strip(), MAX_TRACEBACK)}"
            )
            annotation("error", identifier, details)
    if failures > MAX_ANNOTATIONS:
        annotation(
            "notice",
            "pytest JUnit",
            f"Additional failing test entries omitted: {failures - MAX_ANNOTATIONS}.",
        )
    elif not failures:
        annotation("notice", "pytest JUnit", "No failed tests in JUnit report.")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "report", nargs="?", type=Path, default=Path("reports/pytest.xml")
    )
    args = parser.parse_args()
    report(args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
