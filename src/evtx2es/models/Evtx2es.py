# coding: utf-8
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Generator, Iterable, Union, Any, Optional, Sequence, Callable
import logging
import re

import orjson
from evtx import PyEvtxParser

from .MultiprocessingUtils import SafeMultiprocessingMixin
from .MultiprocessingUtils import mp as mp
from .MultiprocessingUtils import ordered_pool_results


MAX_CONSECUTIVE_PARSE_ERRORS = 100
logger = logging.getLogger(__name__)


class PartialExtractionError(RuntimeError):
    def __init__(self, diagnostics, records=None):
        self.diagnostics = list(diagnostics)
        self.records = records
        super().__init__(
            f"Partial extraction: {len(self.diagnostics)} failure(s); "
            "output is incomplete."
        )



def normalize_shift(shift: Union[str, timedelta, None]) -> Optional[timedelta]:
    if shift == "0":
        return None
    if shift is not None and not isinstance(shift, timedelta):
        raise TypeError("shift must be a timedelta or None")
    return shift


def validate_chunk_size(chunk_size: int) -> None:
    if type(chunk_size) is not int or chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")


def normalize_tags(
    tags: Union[str, Sequence[str], None], builtin_tag: str = "eventlog"
) -> List[str]:
    """Normalize comma-separated strings or tag sequences, preserving order."""
    if tags is None:
        user_tags = []
    elif isinstance(tags, str):
        user_tags = [tag.strip() for tag in tags.split(",") if tag.strip()]
    else:
        user_tags = [tag.strip() for tag in tags if tag.strip()]

    result = []
    for tag in [builtin_tag, *user_tags]:
        if tag not in result:
            result.append(tag)
    return result


def generate_chunks(
    chunk_size: int,
    iterable: Iterable,
    on_parse_error: Optional[Callable[[Exception], None]] = None,
) -> Generator:
    """Generate arbitrarily sized chunks from iterable objects, maximizing data recovery.

    Parser errors are skipped to salvage later records, but repeated errors without
    a successful record eventually raise instead of looping forever.

    Args:
        chunk_size (int): Chunk sizes.
        iterable (Iterable): Original Iterable object.

    Yields:
        Generator: List
    """
    validate_chunk_size(chunk_size)
    iterator = iter(iterable)
    piece = []
    consecutive_errors = 0
    skipped_errors = 0

    try:
        while True:
            try:
                # Extract a single record at a time to isolate parsing errors
                item = next(iterator)
                consecutive_errors = 0
                piece.append(item)

                # Yield the chunk when it reaches the specified size
                if len(piece) == chunk_size:
                    yield piece
                    piece = []

            except StopIteration:
                # End of the iterable reached; yield remaining buffered records
                if piece:
                    yield piece
                break

            except Exception as exc:
                consecutive_errors += 1
                skipped_errors += 1
                if on_parse_error is not None:
                    on_parse_error(exc)
                if consecutive_errors >= MAX_CONSECUTIVE_PARSE_ERRORS:
                    raise RuntimeError(
                        "EVTX parser failed repeatedly without yielding "
                        "a record "
                        f"({consecutive_errors} consecutive errors)"
                    ) from exc

                # Skip transient errors to keep any later valid records.
                continue
    finally:
        if skipped_errors:
            logger.warning(
                "Skipped %d EVTX parser error(s) while recovering records",
                skipped_errors,
            )


def _parse_event_data(record: dict) -> dict:
    """Parse and extract event data from raw record."""
    data = orjson.loads(record.get("data"))
    event = data["Event"]
    system = event["System"]

    # Fix EventID field if it's a dictionary
    if isinstance(system.get("EventID"), dict):
        system["EventID"] = system["EventID"].get("#text")

    # Keep the existing Status behavior until mixed value shapes are checked
    # against the Elasticsearch mapping.
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


def _create_timestamp_field(system_time: str, shift: Optional[timedelta]) -> str:
    """Create timestamp field with optional shift."""
    if shift is not None:
        match = re.search(r"\.(\d+)(?=Z|[+-]\d\d:\d\d$)", system_time)
        fraction = match.group(1) if match else ""
        normalized = system_time.replace("Z", "+00:00")
        if match and len(fraction) > 6:
            start, end = match.span(1)
            normalized = normalized[:start] + fraction[:6] + normalized[end:]
        current_timestamp = datetime.fromisoformat(normalized)
        if current_timestamp.tzinfo is None:
            current_timestamp = current_timestamp.replace(tzinfo=timezone.utc)
        final_timestamp = current_timestamp.astimezone(timezone.utc) + shift
        result = final_timestamp.strftime("%Y-%m-%dT%H:%M:%S")
        precision = max(len(fraction), 6 if final_timestamp.microsecond else 0)
        if precision:
            digits = f"{final_timestamp.microsecond:06d}" + fraction[6:]
            result += "." + digits[:precision]
        return result + "Z"
    return system_time


def _normalize_field_value(key: str, value) -> Any:
    """Normalize specific field values for ProcessId and numeric ranges."""
    if key == "Reason":
        return str(value)

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


def _create_normalized_event_data(
    event_data: dict, original_values: Optional[dict] = None
) -> dict:
    """Normalize fields and optionally retain clamped integers as decimal text."""
    if not event_data or len(event_data) == 0:
        return {}

    normalized_data = {}
    for k, v in event_data.items():
        normalized = _normalize_field_value(k, v)
        normalized_data[k] = normalized
        if (
            original_values is not None
            and type(v) is int
            and type(normalized) is int
            and normalized != v
        ):
            original_values[k] = str(v)

    return normalized_data


def format_record(
    record: dict,
    filepath: str,
    shift: Optional[timedelta],
    additional_tags: Union[str, Sequence[str], None] = None,
) -> dict:
    """Format an Event Log record as structured JSON.

    Args:
        record (dict): Raw eventlog record with 'data' field containing JSON string.
        filepath (str): File path for logging.
        shift (timedelta or None): Timestamp shift.
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
                "event_data": dict (optional),
                "event_data_original": dict (optional, clamped integers as text)
            },
            "userdata": dict (optional),
            "process": {"pid": int, "thread": {"id": int}} (optional),
            "log": {
                "file": {"path": str}
            },
            "tags": [str]
        }

    Optional System fields that are absent in the source remain null.
    """
    tags = normalize_tags(additional_tags)

    # Parse the raw event data
    parsed_data = _parse_event_data(record)

    system = parsed_data["system"]
    channel = system.get("Channel")
    event_id = system["EventID"]
    provider_attrs = (system["Provider"] or {}).get("#attributes") or {}
    provider_name = provider_attrs.get("Name")
    created = ((system.get("TimeCreated") or {}).get("#attributes") or {}).get(
        "SystemTime"
    )
    timestamp = _create_timestamp_field(created, shift) if created is not None else None

    # Create ECS-compliant event fields
    event_fields = {
        "action": (
            f"eventlog-{channel.lower()}-{event_id}"
            if channel is not None
            else f"eventlog-{event_id}"
        ),
        "category": ["host"],
        "type": ["info"],
        "kind": "event",
        "provider": provider_name.lower() if provider_name is not None else None,
        "module": "windows",
        "dataset": "windows.eventlog",
        "code": event_id,
        "created": created,
    }

    # Create Windows-specific fields
    windows_eventlog = {
        "channel": channel,
        "computer_name": system.get("Computer"),
        "event_id": event_id,
        "opcode": system.get("Opcode"),
        "record_id": system.get("EventRecordID"),
        "task": system.get("Task"),
        "version": system.get("Version"),
        "provider": {
            "name": provider_name,
            "guid": provider_attrs.get("Guid"),
        },
    }

    # Keep source values used to assess or correlate events, including zeroes.
    for source, target in (("Level", "level"), ("Keywords", "keywords")):
        if source in system:
            windows_eventlog[target] = system[source]

    security = system.get("Security")
    security_attrs = security.get("#attributes") if isinstance(security, dict) else None
    if isinstance(security_attrs, dict) and "UserID" in security_attrs:
        windows_eventlog["user"] = {"identifier": security_attrs["UserID"]}

    correlation = system.get("Correlation")
    correlation_attrs = (
        correlation.get("#attributes") if isinstance(correlation, dict) else None
    )
    if isinstance(correlation_attrs, dict):
        for source, target in (
            ("ActivityID", "activity_id"),
            ("RelatedActivityID", "related_activity_id"),
        ):
            if source in correlation_attrs:
                windows_eventlog[target] = correlation_attrs[source]

    # Add event_data if present
    original_event_data = {}
    normalized_event_data = _create_normalized_event_data(
        parsed_data["event_data"], original_event_data
    )
    if normalized_event_data:
        windows_eventlog["event_data"] = normalized_event_data
    if original_event_data:
        windows_eventlog["event_data_original"] = original_event_data

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
    filepath: str,
    shift: Optional[timedelta],
    additional_tags: Union[str, Sequence[str], None] = None,
    on_record_error: Optional[Callable[[dict], None]] = None,
) -> List[dict]:
    """Perform formatting for each chunk. (for efficiency)

    Args:
        records (List[str]): A chunk of Event Log records in JSON form.
        filepath (str): Source event log path.
        shift (timedelta or None): Timestamp shift.
        additional_tags (List[str], optional): Additional tags to add to each record.
        on_record_error: Receives a diagnostic for each record that cannot be
            formatted. Without a callback, failures are logged as warnings.

    Returns:
        List[dict]: Successfully formatted records, preserving their input order.
    """

    additional_tags = normalize_tags(additional_tags)

    formatted = []
    for record in records:
        try:
            formatted.append(
                format_record(
                    record, filepath=filepath, shift=shift,
                    additional_tags=additional_tags,
                )
            )
        except Exception as error:
            diagnostic = {
                "source_file": str(Path(filepath).resolve()),
                "error": f"{type(error).__name__}: {error}",
                "stage": "normalization",
            }
            if isinstance(record, dict):
                record_id = record.get("event_record_id")
                if isinstance(record_id, (int, str)):
                    diagnostic["record_id"] = record_id
            if on_record_error is not None:
                on_record_error(diagnostic)
            else:
                logger.warning("Skipped EVTX normalization error: %s", diagnostic)
    return formatted


def _mp_worker(args):
    records, filepath, shift, additional_tags = args
    diagnostics = []
    formatted = process_by_chunk(
        records, filepath, shift, additional_tags, diagnostics.append
    )
    return formatted, diagnostics


class Evtx2es(SafeMultiprocessingMixin):
    def __init__(self, input_path: Path) -> None:
        self.path = input_path
        self.diagnostics = []
        self._file_handle = self.path.open(mode="rb")
        try:
            self.parser = PyEvtxParser(self._file_handle)
        except Exception:
            self._file_handle.close()
            self._file_handle = None
            raise

    def close(self):
        if getattr(self, "_file_handle", None):
            self._file_handle.close()
            self._file_handle = None

    def _record_parse_error(self, error: Exception) -> None:
        self.diagnostics.append(
            {
                "source_file": str(Path(self.path).resolve()),
                "error": f"{type(error).__name__}: {error}",
            }
        )

    def gen_records(
        self,
        shift: Optional[timedelta],
        multiprocess: bool,
        chunk_size: int,
        additional_tags: Union[str, Sequence[str], None] = None,
    ) -> Generator:
        """Generate chunks of formatted Event Log records.

        Args:
            shift (timedelta or None): Timestamp shift.
            multiprocess (bool): Flag to run multiprocessing.
            chunk_size (int): Size of the chunk to be processed for each process.
            additional_tags (List[str], optional): Additional tags to add to each record.

        Yields:
            Generator: Yields List[dict].
        """

        validate_chunk_size(chunk_size)
        self.diagnostics = []

        if multiprocess:
            ctx = self.get_multiprocessing_context()
            worker_count = max(1, self.get_cpu_count())
            with ctx.Pool(worker_count) as pool:
                # Advance the native iterator on this thread; only materialized
                # Python chunks are handed to the shared submission helper.
                tasks = (
                    (chunk, str(self.path), shift, additional_tags)
                    for chunk in generate_chunks(
                        chunk_size, self.parser.records_json(), self._record_parse_error
                    )
                )
                for formatted, diagnostics in ordered_pool_results(
                    pool, _mp_worker, tasks, worker_count * 2
                ):
                    self.diagnostics.extend(diagnostics)
                    if formatted:
                        yield formatted
        else:
            for records in generate_chunks(
                chunk_size, self.parser.records_json(), self._record_parse_error
            ):
                formatted = process_by_chunk(
                    records, str(self.path), shift, additional_tags,
                    self.diagnostics.append,
                )
                if formatted:
                    yield formatted
