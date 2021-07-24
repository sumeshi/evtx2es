# coding: utf-8
from datetime import datetime, timedelta
from itertools import chain
from pathlib import Path
from typing import List, Generator, Iterable, Union
from itertools import islice
from multiprocessing import Pool, cpu_count

import orjson
from evtx import PyEvtxParser


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


def format_record(record: dict, filepath: str, shift: Union[str, datetime]):
    """Formatting each Eventlog records.

    Args:
        records (List[str]): chunk of Eventlog records(json).
        shift (str): datetime string

    Yields:
        List[dict]: Eventlog records.
    """

    record["data"] = orjson.loads(record.get("data"))

    eventid_field = record.get("data", {}).get("Event", {}).get("System", {}).get("EventID")
    if type(eventid_field) is dict:
        record["data"]["Event"]["System"]["EventID"] = eventid_field.get("#text")

    try:
        status = record.get("data").get("Event").get("EventData").get("Status")
        record["data"]["Event"]["EventData"]["Status"] = None
    except Exception:
        pass

    # Convert data according to ECS (sort of)
    # First copy system fields
    record["winlog"] = {
        "channel": record["data"]["Event"]["System"]["Channel"],
        "computer_name": record["data"]["Event"]["System"]["Computer"],
        "event_id": record["data"]["Event"]["System"]["EventID"],
        "opcode": record["data"]["Event"]["System"].get("Opcode"),
        "provider_guid": record["data"]["Event"]["System"]["Provider"][
            "#attributes"
        ].get("Guid"),
        "provider_name": record["data"]["Event"]["System"]["Provider"][
            "#attributes"
        ]["Name"],
        "record_id": record["data"]["Event"]["System"]["EventRecordID"],
        "task": record["data"]["Event"]["System"]["Task"],
        "version": record["data"]["Event"]["System"].get("Version"),
    }
    try:
        record["winlog"]["process"] = {
            "pid": record["data"]["Event"]["System"]["Execution"]["#attributes"][
                "ProcessID"
            ],
            "thread_id": record["data"]["Event"]["System"]["Execution"][
                "#attributes"
            ]["ThreadID"],
        }
    except KeyError:
        pass

    except TypeError:
        pass

    try:
        record["userdata"] = {
            "address": record["data"]["Event"]["UserData"]["EventXML"]["Address"],
            "sessionid": record["data"]["Event"]["UserData"]["EventXML"][
                "SessionID"
            ],
            "user": record["data"]["Event"]["UserData"]["EventXML"]["User"],
        }
    except KeyError:
        pass

    except TypeError:
        pass

    record.update(
        {
            "log": {"file": {"name": filepath}},
            "event": {
                "code": record["winlog"]["event_id"],
                "created": record["data"]["Event"]["System"]["TimeCreated"][
                    "#attributes"
                ]["SystemTime"],
            },
        }
    )

    # Shift timestamp
    if shift != '0':
        current_timestamp = datetime.strptime(record["event"]["created"], "%Y-%m-%d"'T'"%H:%M:%S.%fZ")
        final_timestamp = current_timestamp + timedelta(seconds=shift.seconds) + timedelta(days=shift.days)
        record["@timestamp"] = final_timestamp.strftime("%Y-%m-%d"'T'"%H:%M:%S.%fZ")
    else:
        record["@timestamp"] = record["event"]["created"]

    # Move event attributes to ECS location
    record["winlog"]["event_data"] = record["data"]["Event"].get(
        "EventData", dict()
    )
    del record["data"]
    if (
        record["winlog"]["event_data"] is None
        or len(record["winlog"]["event_data"]) == 0
    ):  # remove event_data fields if empty
        del record["winlog"]["event_data"]
    else:
        if record["winlog"]["event_data"]:
            for k, v in record["winlog"]["event_data"].items():
                # Normalize some known problematic fields with values switching between integers and strings with hexadecimal notation to integers
                if k in ("ProcessId") and type(v) == str:
                    if v.startswith("0x"):
                        record["winlog"]["event_data"][k] = int(v, 16)
                    else:
                        try:
                            record["winlog"]["event_data"][k] = int(v)
                        except ValueError:
                            record["winlog"]["event_data"][k] = 0

                # Maximum limit of numeric values in Elasticsearch
                if type(v) is int:
                    if v < -(2 ** 63):
                        record["winlog"]["event_data"][k] = -(2 ** 63)
                    elif v > 2 ** 63 - 1:
                        record["winlog"]["event_data"][k] = 2 ** 63 - 1

    return record


def process_by_chunk(records: List[str], filepath: Union[Generator, str], shift: Union[Generator, str, datetime]) -> List[dict]:
    """Perform formatting for each chunk. (for efficiency)

    Args:
        records (List[str]): chunk of Eventlog records(json).
        filepath (List[str]): list with 1 element.
        shift (List[Union[str, datetime]]): list with 1 element

    Yields:
        List[dict]: Eventlog records list.
    """

    filepath = filepath if type(filepath) is str else filepath.__next__()
    shift = shift if type(shift) is str else shift.__next__()

    concatenated_json: str = f"[{','.join([orjson.dumps(record).decode('utf-8') for record in records])}]"
    record_list: List[dict] = orjson.loads(concatenated_json)

    return [
        format_record(record, filepath=filepath, shift=shift) for record in record_list
    ]


class Evtx2es(object):
    def __init__(self, input_path: Path) -> None:
        self.path = input_path
        self.parser = PyEvtxParser(self.path.open(mode="rb"))

    def gen_records(self, shift: Union[str, datetime], multiprocess: bool, chunk_size: int) -> Generator:
        """Generates the formatted Eventlog records chunks.

        Args:
            multiprocess (bool): Flag to run multiprocessing.
            chunk_size (int): Size of the chunk to be processed for each process.

        Yields:
            Generator: Yields List[dict].
        """

        gen_path = iter(lambda: str(self.path), None)
        gen_shift = iter(lambda: shift, None)

        if multiprocess:
            with Pool(cpu_count()) as pool:
                results = pool.starmap_async(
                    process_by_chunk,
                    zip(
                        generate_chunks(chunk_size, self.parser.records_json()),
                        gen_path,
                        gen_shift,
                    )
                )
                yield list(chain.from_iterable(results.get(timeout=None)))
        else:
            buffer: List[List[dict]] = list()
            for records in generate_chunks(chunk_size, self.parser.records_json()):
                if chunk_size <= len(buffer):
                    yield list(chain.from_iterable(buffer))
                    buffer.clear()
                else:
                    buffer.append(process_by_chunk(records, gen_path, gen_shift))
            else:
                yield list(chain.from_iterable(buffer))
