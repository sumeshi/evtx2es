"""Generate a synthetic EVTX with mixed native Status values.

This is a BinXML test artifact, not a Windows-captured event log. Inline
EventData/Status elements allow the native parser to expose JSON null and
objects as well as scalar types. Arrays are tested separately at the parser's
JSON boundary: its WStringArray serializer expands them into separate fields.
No existing captured fixture is changed and no additional parser is needed.
"""

from pathlib import Path
import struct
import zlib

STATUSES = (
    "0xC000013A",
    "0xc000013a",
    3221225786,
    0,
    "0",
    True,
    "true",
    False,
    "false",
    None,
    "null",
    {"Code": "0x20", "Message": "失敗"},
    2**64 - 1,
    -1,
    "2026-01-01",
)


class _BinXml:
    """Write one resident template containing the fixture's literal values."""

    def __init__(self, offset, record_id):
        self.base = offset + 24  # Record header precedes BinXML.
        self.data = bytearray(
            b"\x0f\x01\x01\x00"  # Fragment header.
            + b"\x0c\x01"  # Template instance.
            + struct.pack("<II", record_id, self.base + 14)
            + struct.pack("<IQQI", 0, record_id, 0, 0)  # Resident template.
        )

    def _name(self, name):
        self.data.extend(struct.pack("<I", self.base + len(self.data) + 4))
        name_hash = 0
        for char in name:
            name_hash = (name_hash * 65599 + ord(char)) & 0xFFFF
        self.data.extend(struct.pack("<IHH", 0, name_hash, len(name)))
        self.data.extend(name.encode("utf-16le") + b"\0\0")

    def _scalar(self, value):
        if type(value) is bool:
            kind, payload = 0x0D, struct.pack("<I", value)
        elif type(value) is int:
            kind = 0x09 if value < 0 else 0x0A
            payload = struct.pack("<q" if value < 0 else "<Q", value)
        else:
            kind = 0x01
            encoded = value.encode("utf-16le")
            payload = struct.pack("<H", len(encoded) // 2) + encoded
        self.data.extend(bytes((0x05, kind)) + payload)

    def _element(self, name, inside=lambda: None, attributes=()):
        start = len(self.data)
        self.data.append(0x41 if attributes else 0x01)
        self.data.extend(struct.pack("<HI", 0xFFFF, 0))
        self._name(name)
        if attributes:
            size_offset = len(self.data)
            self.data.extend(bytes(4))
            attribute_start = len(self.data)
            for key, value in attributes:
                self.data.append(0x06)
                self._name(key)
                self._scalar(value)
            struct.pack_into(
                "<I", self.data, size_offset, len(self.data) - attribute_start
            )
        self.data.append(0x02)  # Close start element.
        inside()
        self.data.append(0x04)  # End element.
        struct.pack_into("<I", self.data, start + 3, len(self.data) - start - 7)

    def _value(self, value):
        if value is None:
            return  # An empty ordinary element becomes JSON null.
        if isinstance(value, dict):
            for key, child in value.items():
                self._element(key, lambda child=child: self._value(child))
        else:
            self._scalar(value)

    def event(self, status, record_id):
        def system():
            self._element("Provider", attributes=(("Name", "Status-Fixture"),))
            self._element("EventID", lambda: self._scalar(1))
            self._element("Channel", lambda: self._scalar("Security"))
            self._element("EventRecordID", lambda: self._scalar(record_id))
            self._element(
                "TimeCreated",
                attributes=(("SystemTime", "2026-01-01T00:00:00Z"),),
            )

        def event():
            self._element("System", system)
            self._element(
                "EventData",
                lambda: self._element("Status", lambda: self._value(status)),
            )

        self._element("Event", event)
        self.data.append(0x00)  # End template stream.
        struct.pack_into("<I", self.data, 34, len(self.data) - 38)
        self.data.extend(bytes(4))  # No substitutions: all values are literals.
        return self.data


def create_artifact(directory: Path) -> Path:
    """Write one complete, checksummed chunk and return the EVTX path."""
    directory.mkdir(parents=True, exist_ok=True)
    chunk = bytearray(65536)
    chunk[:8] = b"ElfChnk\0"
    count = len(STATUSES)
    struct.pack_into("<QQQQI", chunk, 8, 1, count, 1, count, 128)
    offset = 512
    for record_id, status in enumerate(STATUSES, 1):
        xml = _BinXml(offset, record_id).event(status, record_id)
        size = (24 + len(xml) + 4 + 7) // 8 * 8
        record = (
            struct.pack("<IIQQ", 0x2A2A, size, record_id, 134116992000000000)
            + xml
            + bytes(size - 28 - len(xml))
            + struct.pack("<I", size)
        )
        chunk[offset : offset + size] = record
        last_record = offset
        offset += size
    struct.pack_into("<II", chunk, 44, last_record, offset)
    struct.pack_into("<I", chunk, 52, zlib.crc32(chunk[512:offset]))
    struct.pack_into("<I", chunk, 124, zlib.crc32(chunk[:120] + chunk[128:512]))
    header = bytearray(4096)
    header[:8] = b"ElfFile\0"
    struct.pack_into("<QQQIHHHH", header, 8, 0, 0, count + 1, 128, 1, 3, 4096, 1)
    struct.pack_into("<I", header, 124, zlib.crc32(header[:120]))
    destination = directory / "mixed-status.evtx"
    destination.write_bytes(header + chunk)
    return destination
