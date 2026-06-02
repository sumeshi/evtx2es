# coding: utf-8
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Generator, Iterable, Union, Any, Optional
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
    """Generate arbitrarily sized chunks from iterable objects, maximizing data recovery.

    When dealing with EVTX files recovered via carving from unallocated space, 
    the data is frequently incomplete, overwritten, or heavily corrupted (garbage data).
    This function replaces `itertools.islice` with manual iteration to gracefully 
    handle both expected parsing errors (like `RuntimeError` for bad chunk headers) 
    and unexpected exceptions. The primary goal is to salvage as many intact 
    records as possible without crashing the entire extraction process.

    Args:
        chunk_size (int): Chunk sizes.
        iterable (Iterable): Original Iterable object.

    Yields:
        Generator: List
    """
    iterator = iter(iterable)
    piece = []

    while True:
        try:
            # Extract a single record at a time to isolate parsing errors
            item = next(iterator)
            piece.append(item)

            # Yield the chunk when it reaches the specified size
            if len(piece) == chunk_size:
                yield piece
                piece = []

        except StopIteration:
            # End of the iterable reached; yield any remaining records in the buffer
            if piece:
                yield piece
            break

        except RuntimeError:
            # Catch specific EVTX parser errors (e.g., corrupted chunk headers).
            # Bypassing these allows us to recover subsequent valid records.
            continue

        except Exception:
            # Catch-all for unexpected errors caused by heavily corrupted carved data.
            # In forensic carving, encountering unpredictable garbage data is common.
            # We catch these to ensure the parser survives and extracts all possible data
            # instead of halting the entire pipeline.
            continue


def _parse_event_data(record: dict) -> dict:
    """Parse and extract event data from raw record."""
    data = orjson.loads(record.get("data"))
    event = data["Event"]
    system = event["System"]

    # Fix EventID field if it's a dictionary
    if isinstance(system.get("EventID"), dict):
        system["EventID"] = system["EventID"].get("#text")

    # Clear Status field in EventData if present
    try:
        if "EventData" in event and event["EventData"] is not None and "Status" in event["EventData"]:
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
        try:
            current_timestamp = datetime.strptime(system_time, "%Y-%m-%dT%H:%M:%S.%fZ")
        except ValueError:
            current_timestamp = datetime.strptime(system_time, "%Y-%m-%dT%H:%M:%SZ")
        final_timestamp = current_timestamp + timedelta(seconds=shift.seconds) + timedelta(days=shift.days)
        return final_timestamp.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    else:
        return system_time


def _normalize_field_value(key: str, value) -> Any:
    """Normalize specific field values for ProcessId and numeric ranges."""
    # Normalize ProcessId fields
    if key == "ProcessId" and isinstance(value, str):
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
    additional_tags: Optional[List[str]] = None,
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
    records: List[dict],
    filepath: Union[Generator, str],
    shift: Union[Generator, str, datetime],
    additional_tags: Union[Generator, Optional[List[str]]] = None,
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

    # Accept both raw values (multiprocess path) and generators (single-process path)
    filepath = filepath if isinstance(filepath, str) else next(filepath)
    shift = shift if isinstance(shift, (str, datetime)) else next(shift)
    if isinstance(additional_tags, list) or additional_tags is None:
        pass
    else:
        additional_tags = next(additional_tags)

    record_list = records

    return [
        format_record(
            record, filepath=filepath, shift=shift, additional_tags=additional_tags
        )
        for record in record_list
    ]


def _mp_worker(args):
    records, filepath, shift, additional_tags = args
    return process_by_chunk(records, filepath, shift, additional_tags)


class Evtx2es(SafeMultiprocessingMixin):
    def __init__(self, input_path: Path) -> None:
        self.path = input_path
        self._file_handle = self.path.open(mode="rb")
        self.parser = PyEvtxParser(self._file_handle)

    def close(self):
        if getattr(self, "_file_handle", None):
            self._file_handle.close()
            self._file_handle = None

    def gen_records(
        self,
        shift: Union[str, datetime],
        multiprocess: bool,
        chunk_size: int,
        additional_tags: Optional[List[str]] = None,
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

        def gen_tags():
            while True:
                yield additional_tags

        gen_tags = gen_tags()

        if multiprocess:
            ctx = self.get_multiprocessing_context()
            with ctx.Pool(self.get_cpu_count()) as pool:
                yield from pool.imap(
                    _mp_worker,
                    (
                        (c, str(self.path), shift, additional_tags)
                        for c in generate_chunks(
                            chunk_size, self.parser.records_json()
                        )
                    ),
                )
        else:
            for records in generate_chunks(chunk_size, self.parser.records_json()):
                yield process_by_chunk(records, gen_path, gen_shift, gen_tags)
