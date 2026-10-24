"""Native-parser fixture shared by binary and Elasticsearch validation.

Three records from JPCERTCC/LogonTracer sample/Security.evtx (MD5 8ba673df16853ee6d1bb6358deed35e3). Two SubjectLogonId BinXML substitutions were changed to UInt64 boundary values; the file/chunk checksums were recomputed. These boundary values were not captured on Windows.
Source: https://github.com/JPCERTCC/LogonTracer/blob/638c1a4e6095cbf530ada057e7403ff8636f601c/sample/Security.evtx
"""

from hashlib import sha256
from pathlib import Path

PACKAGE = "evtx2es"
JSON_COMMAND = "evtx2json"
TIMELINE_MODES = (None,)
SUPPORTS_MULTIPROCESSING = True
API_KWARGS = {}
CLI_ARGS = ()


def create_artifact(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    payload = (
        Path(__file__).with_name("fixtures") / "security-three-records.bin"
    ).read_bytes()
    if (
        sha256(payload).hexdigest()
        != "9368418b6d2264e98cd5da8772bc80d7be43c784f93ba163de25a44a7a77fd1d"
    ):
        raise RuntimeError("Native validation fixture checksum mismatch")
    destination = directory / "Security.evtx"
    destination.write_bytes(payload)
    return destination
