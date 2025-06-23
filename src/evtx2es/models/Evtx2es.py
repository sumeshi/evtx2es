# coding: utf-8
from datetime import datetime, timedelta
from itertools import chain
from pathlib import Path
from typing import List, Generator, Iterable, Union, Any
from itertools import islice
import multiprocessing as mp
import sys
import os

import orjson
from evtx import PyEvtxParser


class SafeMultiprocessingMixin:
    """Safe multiprocessing management class for Python 3.13 compatibility"""

    @staticmethod
    def get_multiprocessing_context() -> mp.context:
        """Get safe multiprocessing context"""
        # Use spawn for Python 3.13+ or test environments to avoid fork() issues
        if sys.version_info >= (3, 13) or "pytest" in sys.modules:
            try:
                ctx = mp.get_context("spawn")
            except RuntimeError:
                ctx = mp.get_context()
        else:
            ctx = mp.get_context()

        return ctx

    @staticmethod
    def get_cpu_count() -> int:
        """Get CPU count safely"""
        try:
            return mp.cpu_count()
        except NotImplementedError:
            return os.cpu_count() or 1


def generate_chunks(chunk_size: int, iterable: Iterable) -> Generator:
    """Generate arbitrarily sized chunks from iterable objects.

    Args:
        chunk_size (int): Chunk sizes.
        iterable (Iterable): Original Iterable object.

    Yields:
        Generator: List
    """
    i = iter(iterable)
    piece = list(islice(i, chunk_size))
    while piece:
        yield piece
        piece = list(islice(i, chunk_size))


def _parse_event_data(record: dict) -> dict:
    """Parse and extract event data from raw record."""
    data = orjson.loads(record.get("data"))
    event = data["Event"]
    system = event["System"]

    # Fix EventID field if it's a dictionary
    if isinstance(system.get("EventID"), dict):
        system["EventID"] = system["EventID"].get("#text")

    # Clear Status field in EventData (matches original behavior)
    try:
        status = event.get("EventData", {}).get("Status")
        if "EventData" in event and event["EventData"] is not None:
            event["EventData"]["Status"] = None
    except Exception:
        pass

    return {
        "system": system,
        "event_data": event.get("EventData", {}),
        "user_data": event.get("UserData", {}),
    }


def _create_timestamp_field(system_time: str, shift: Union[str, datetime]) -> str:
    """Create timestamp field with optional shift."""
    if shift != "0" and isinstance(shift, datetime):
        current_timestamp = datetime.strptime(
            system_time, "%Y-%m-%d" "T" "%H:%M:%S.%fZ"
        )
        final_timestamp = (
            current_timestamp
            + timedelta(seconds=shift.seconds)
            + timedelta(days=shift.days)
        )
        return final_timestamp.strftime("%Y-%m-%d" "T" "%H:%M:%S.%fZ")
    else:
        return system_time


def _normalize_field_value(key: str, value) -> Any:
    """Normalize specific field values for ProcessId and numeric ranges."""
    # Normalize ProcessId fields
    if key in ("ProcessId") and isinstance(value, str):
        if value.startswith("0x"):
            return int(value, 16)
        else:
            try:
                return int(value)
            except ValueError:
                return 0

    # Limit numeric values for Elasticsearch
    if isinstance(value, int):
        if value < -(2**63):
            return -(2**63)
        elif value > 2**63 - 1:
            return 2**63 - 1

    return value


def _create_normalized_event_data(event_data: dict) -> dict:
    """Create normalized event_data fields."""
    if not event_data or len(event_data) == 0:
        return {}

    normalized_data = {}
    for k, v in event_data.items():
        normalized_data[k] = _normalize_field_value(k, v)

    return normalized_data


def format_record(
    record: dict,
    filepath: str,
    shift: Union[str, datetime],
    additional_tags: List[str] = None,
) -> dict:
    """Format Eventlog record into structured JSON.

    Args:
        record (dict): Raw eventlog record with 'data' field containing JSON string.
        filepath (str): File path for logging.
        shift (Union[str, datetime]): Timestamp shift value.
        additional_tags (List[str], optional): Additional tags to add to the record.

    Returns:
        dict: Formatted eventlog record with structure:
        {
            "@timestamp": str,
            "event": {
                "action": str,
                "category": [str],
                "type": [str],
                "kind": "event",
                "provider": str,
                "module": "windows",
                "dataset": "windows.eventlog",
                "code": int,
                "created": str
            },
            "winlog": {
                "channel": str,
                "computer_name": str,
                "event_id": int,
                "record_id": int,
                "opcode": int,
                "task": int,
                "version": int,
                "provider": {"name": str, "guid": str},
                "event_data": dict (optional)
            },
            "userdata": dict (optional),
            "process": {"pid": int, "thread": {"id": int}} (optional),
            "log": {
                "file": {"path": str}
            },
            "tags": [str]
        }
    """
    # User defined tags
    tags = ["eventlog"]
    if additional_tags:
        tags.extend(additional_tags)

    # Parse the raw event data
    parsed_data = _parse_event_data(record)

    system = parsed_data["system"]
    channel = system["Channel"]
    event_id = system["EventID"]
    provider_attrs = system["Provider"]["#attributes"]
    timestamp = _create_timestamp_field(
        system["TimeCreated"]["#attributes"]["SystemTime"], shift
    )

    # Create ECS-compliant event fields
    event_fields = {
        "action": f"eventlog-{channel.lower()}-{event_id}",
        "category": ["host"],
        "type": ["info"],
        "kind": "event",
        "provider": provider_attrs["Name"].lower(),
        "module": "windows",
        "dataset": "windows.eventlog",
        "code": event_id,
        "created": system["TimeCreated"]["#attributes"]["SystemTime"],
    }

    # Create Windows-specific fields
    windows_eventlog = {
        "channel": channel,
        "computer_name": system["Computer"],
        "event_id": event_id,
        "opcode": system.get("Opcode"),
        "record_id": system["EventRecordID"],
        "task": system["Task"],
        "version": system.get("Version"),
        "provider": {
            "name": provider_attrs["Name"],
            "guid": provider_attrs.get("Guid"),
        },
    }

    # Add event_data if present
    normalized_event_data = _create_normalized_event_data(parsed_data["event_data"])
    if normalized_event_data:
        windows_eventlog["event_data"] = normalized_event_data

    # Build the final ECS-compliant result object
    result = {
        "@timestamp": timestamp,
        "event": event_fields,
        "winlog": windows_eventlog,
        # user_data (optional)
        # process (optional)
        # log.file.path
        # tags
    }

    # Add userdata if present
    if parsed_data["user_data"]:
        result["userdata"] = parsed_data["user_data"]

    # Add process fields if available
    try:
        execution_attrs = system["Execution"]["#attributes"]
        result["process"] = {
            "pid": int(execution_attrs["ProcessID"]),
            "thread": {"id": int(execution_attrs["ThreadID"])},
        }
    except (KeyError, TypeError, ValueError):
        pass

    result["log"] = {"file": {"path": str(Path(filepath).resolve())}}
    result["tags"] = tags

    return result


def process_by_chunk(
    records: List[str],
    filepath: Union[Generator, str],
    shift: Union[Generator, str, datetime],
    additional_tags: Union[Generator, List[str]] = None,
) -> List[dict]:
    """Perform formatting for each chunk. (for efficiency)

    Args:
        records (List[str]): chunk of Eventlog records(json).
        filepath (List[str]): list with 1 element.
        shift (List[Union[str, datetime]]): list with 1 element
        additional_tags (List[str], optional): Additional tags to add to each record.

    Yields:
        List[dict]: Eventlog records list.
    """

    filepath = filepath if type(filepath) is str else filepath.__next__()
    shift = shift if type(shift) is str else shift.__next__()
    additional_tags = (
        additional_tags
        if isinstance(additional_tags, list)
        else (additional_tags.__next__() if additional_tags else None)
    )

    concatenated_json: str = (
        f"[{','.join([orjson.dumps(record).decode('utf-8') for record in records])}]"
    )
    record_list: List[dict] = orjson.loads(concatenated_json)

    return [
        format_record(
            record, filepath=filepath, shift=shift, additional_tags=additional_tags
        )
        for record in record_list
    ]


class Evtx2es(SafeMultiprocessingMixin):
    def __init__(self, input_path: Path) -> None:
        self.path = input_path
        self.parser = PyEvtxParser(self.path.open(mode="rb"))

    def gen_records(
        self,
        shift: Union[str, datetime],
        multiprocess: bool,
        chunk_size: int,
        additional_tags: List[str] = None,
    ) -> Generator:
        """Generates the formatted Eventlog records chunks.

        Args:
            shift (Union[str, datetime]): Timestamp shift value.
            multiprocess (bool): Flag to run multiprocessing.
            chunk_size (int): Size of the chunk to be processed for each process.
            additional_tags (List[str], optional): Additional tags to add to each record.

        Yields:
            Generator: Yields List[dict].
        """

        gen_path = iter(lambda: str(self.path), None)
        gen_shift = iter(lambda: shift, None)

        # Create a proper generator for additional_tags
        def gen_tags():
            while True:
                yield additional_tags

        gen_tags = gen_tags()

        if multiprocess:
            # Use safe context for Python 3.13 compatibility
            ctx = self.get_multiprocessing_context()
            with ctx.Pool(self.get_cpu_count()) as pool:
                results = pool.starmap_async(
                    process_by_chunk,
                    zip(
                        generate_chunks(chunk_size, self.parser.records_json()),
                        gen_path,
                        gen_shift,
                        gen_tags,
                    ),
                )
                yield list(chain.from_iterable(results.get(timeout=None)))
        else:
            buffer: List[List[dict]] = list()
            for records in generate_chunks(chunk_size, self.parser.records_json()):
                if chunk_size <= len(buffer):
                    yield list(chain.from_iterable(buffer))
                    buffer.clear()
                else:
                    buffer.append(
                        process_by_chunk(records, gen_path, gen_shift, gen_tags)
                    )
            else:
                yield list(chain.from_iterable(buffer))
