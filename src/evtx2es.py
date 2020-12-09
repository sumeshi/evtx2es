#!/usr/bin/env python3
# coding: utf-8
import json
import argparse
import traceback
from pathlib import Path
from typing import List, Generator
from hashlib import sha1

from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

from evtx import PyEvtxParser
from tqdm import tqdm


class ElasticsearchUtils(object):
    def __init__(self, hostname: str, port: int, scheme: str, login: str, pwd: str):
        if login == "":
            self.es = Elasticsearch(host=hostname, port=port, scheme=scheme)
        else:
            self.es = Elasticsearch(host=hostname, port=port, scheme=scheme,verify_certs=False, http_auth=(login,pwd))

    def calc_hash(self, record: dict) -> str:
        """Calculate hash value from record.

        Args:
            record (dict): Eventlog record.

        Returns:
            str: Hash value
        """
        return sha1(json.dumps(record, sort_keys=True).encode()).hexdigest()

    def bulk_indice(self, records: List[dict], index_name: str) -> None:
        """Bulk indices the documents into Elasticsearch.

        Args:
            records (List[dict]): List of each records read from evtx files.
            index_name (str): Target Elasticsearch Index.
        """
        bulk(
            self.es,
            [
                {"_id": self.calc_hash(record), "_index": index_name, "_source": record}
                for record in records
            ],
            raise_on_error=False,
        )


class Evtx2es(object):
    def __init__(self, filepath: str):
        self.path = Path(filepath).resolve()
        self.parser = PyEvtxParser(self.path.open(mode="rb"))

    def format_record(self, record: dict) -> dict:
        record["data"] = json.loads(record.get("data"))

        eventid_field = record.get("data").get("Event").get("System").get("EventID")
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
                "log": {"file": {"name": str(self.path)}},
                "event": {
                    "code": record["winlog"]["event_id"],
                    "created": record["data"]["Event"]["System"]["TimeCreated"][
                        "#attributes"
                    ]["SystemTime"],
                },
            }
        )
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

    def gen_records(self, size: int) -> Generator:
        """A generator that reads records from an Evtx file and generates a dict for each record.

        Args:
            size (int): Buffer size.

        Yields:
            Generator: Yields List[dict].
        """

        buffer: List[dict] = list()

        # generates records
        for record in self.parser.records_json():

            formatted_record: dict = self.format_record(record)
            buffer.append(formatted_record)

            if len(buffer) >= size:
                yield buffer
                buffer.clear()
        else:
            yield buffer


def evtx2es(
    filepath: str,
    host: str = "localhost",
    port: int = 9200,
    index: str = "evtx2es",
    size: int = 500,
    scheme: str = "http",
    login: str = "",
    pwd: str = ""
):
    """Fast import of Windows EventLogs(.evtx) into Elasticsearch.

    Args:
        filepath (str):
            Windows EventLogs to import into Elasticsearch.

        host (str, optional):
            Elasticsearch host address. Defaults to "localhost".

        port (int, optional):
            Elasticsearch port number. Defaults to 9200.

        index (str, optional):
            Name of the index to create. Defaults to "evtx2es".

        size (int, optional):
            Buffer size for BulkIndice at a time. Defaults to 500.

        scheme (str, optional):
            Elasticsearch address scheme. Defaults to "http".
        login (str,optional):
            Elasticsearch login to connect into.
        pwd (str,optional):
            Elasticsearch password associated with the login provided.
    """
    es = ElasticsearchUtils(hostname=host, port=port, scheme=scheme,login=login,pwd=pwd)
    r = Evtx2es(filepath)

    for records in tqdm(r.gen_records(size)):
        try:
            es.bulk_indice(records, index)
        except Exception:
            traceback.print_exc()


def evtx2json(filepath: str) -> List[dict]:
    """Convert evtx to json.

    Args:
        filepath (str): Input EventLog(evtx) file.

    Note:
        Since the content of the file is loaded into memory at once,
        it requires the same amount of memory as the file to be loaded.
    """
    r = Evtx2es(filepath)

    buffer: List[dict] = sum(list(tqdm(r.gen_records(500))), list())
    return buffer


def console_evtx2es():
    """ This function is loaded when used from the console.
    """

    # Args
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "evtxfiles",
        nargs="+",
        type=Path,
        help="Windows EVTX files or directories containing them.",
    )

    # Options
    parser.add_argument("--host", default="localhost", help="Elasticsearch host")
    parser.add_argument("--port", default=9200, help="Elasticsearch port number")
    parser.add_argument("--index", default="evtx2es", help="Index name")
    parser.add_argument("--size", default=500, help="Bulk insert buffer size")
    parser.add_argument("--scheme", default="http", help="Scheme to use (http, https)")
    parser.add_argument("--login", default="elastic", help="Login to use to connect to Elastic database")
    parser.add_argument("--pwd", default="", help="Password associated with the login")
    args = parser.parse_args()

    # Target files
    evtxfiles = list()
    for evtxfile in args.evtxfiles:
        if evtxfile.is_dir():
            evtxfiles.extend(evtxfile.glob("**/*.evtx"))
            evtxfiles.extend(evtxfile.glob("**/*.EVTX"))
        else:
            evtxfiles.append(evtxfile)

    # Indexing evtx files
    for evtxfile in evtxfiles:
        print(f"Currently Importing {evtxfile}")
        evtx2es(
            filepath=evtxfile,
            host=args.host,
            port=int(args.port),
            index=args.index,
            size=int(args.size),
            scheme=args.scheme,
            login=args.login,
            pwd=args.pwd
        )
        print()

    print("Import completed.")


def console_evtx2json():
    """ This function is loaded when used from the console.
    """

    # Args
    parser = argparse.ArgumentParser()
    parser.add_argument("evtxfile", type=Path, help="Windows EVTX file.")
    parser.add_argument("jsonfile", type=Path, help="Output json file path.")
    args = parser.parse_args()

    # Convert evtx to json file.
    print(f"Converting {args.evtxfile}")
    o = Path(args.jsonfile)
    o.write_text(json.dumps(evtx2json(filepath=args.evtxfile), indent=2))
    print()

    print("Convert completed.")


if __name__ == "__main__":
    console_evtx2es()
