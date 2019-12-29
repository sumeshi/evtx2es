#!/usr/bin/env python3
# coding: utf-8
import json
import argparse
import traceback

from pathlib import Path
from typing import List, Generator

from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

from evtx import PyEvtxParser
from tqdm import tqdm


class ElasticsearchUtils(object):
    def __init__(self, hostname: str, port: int) -> None:
        self.es = Elasticsearch(host=hostname, port=port)

    def bulk_indice(self, records, index_name: str, type_name: str) -> None:
        bulk(self.es, [
            {
                '_index': index_name,
                '_type': type_name,
                '_source': record
            } for record in records],
            raise_on_error=False
        )


class Evtx2es(object):
    def __init__(self, filepath: str) -> None:
        self.path = Path(filepath)
        self.parser = PyEvtxParser(self.path.open(mode='rb'))

    def gen_json(self, size: int) -> Generator:
        buffer: List[dict] = []
        for record in self.parser.records_json():
            record['data'] = json.loads(record.get('data'))

            eventid_field = record.get('data').get('Event').get('System').get('EventID')
            if type(eventid_field) is dict:
                record['data']['Event']['System']['EventID'] = eventid_field.get('#text')

            try:
                status = record.get('data').get('Event').get('EventData').get('Status')
                record['data']['Event']['EventData']['Status'] = None
            except Exception:
                pass

            # Convert data according to ECS (sort of)
            # First copy system fields
            record['winlog'] = {
                    'channel': record['data']['Event']['System']['Channel'],
                    'computer_name': record['data']['Event']['System']['Computer'],
                    'event_id': record['data']['Event']['System']['EventID'],
                    'opcode': record['data']['Event']['System'].get('Opcode'),
                    'provider_guid': record['data']['Event']['System']['Provider']['#attributes'].get('Guid'),
                    'provider_name': record['data']['Event']['System']['Provider']['#attributes']['Name'],
                    'record_id': record['data']['Event']['System']['EventRecordID'],
                    'task': record['data']['Event']['System']['Task'],
                    'version': record['data']['Event']['System'].get('Version'),
                    }
            try:
                record['winlog']['process'] = {
                        'pid': record['data']['Event']['System']['Execution']['#attributes']['ProcessID'],
                        'thread_id': record['data']['Event']['System']['Execution']['#attributes']['ThreadID'],
                        }
            except KeyError:
                pass

            record.update({
                'log': {
                    'file': {
                            'name': str(self.path)
                        }
                    },
                'event': {
                    'code': record['winlog']['event_id'],
                    'created': record['data']['Event']['System']['TimeCreated']['#attributes']['SystemTime'],
                    }
                })
            record['@timestamp'] = record['event']['created']

            # Move event attributes to ECS location
            record['winlog']['event_data'] = record['data']['Event'].get('EventData', dict())
            del record['data']
            if record['winlog']['event_data'] is None or len(record['winlog']['event_data']) == 0:    # remove event_data fields if empty
                del record['winlog']['event_data']
            else:
                for k, v in record['winlog']['event_data'].items():
                    # Normalize some known problematic fields with values switching between integers and strings with hexadecimal notation to integers
                    if k in ('ProcessId') and type(v) == str:
                        if v.startswith("0x"):
                            record['winlog']['event_data'][k] = int(v, 16)
                        else:
                            try:
                                record['winlog']['event_data'][k] = int(v)
                            except ValueError:
                                record['winlog']['event_data'][k] = 0

                    # Maximum limit of numeric values in Elasticsearch
                    if type(v) is int:
                        if v < -2 ** 63:
                            record['winlog']['event_data'][k] = -2 ** 63
                        elif v > 2 ** 63 - 1:
                            record['winlog']['event_data'][k] = 2 ** 63 - 1

            buffer.append(record)

            if len(buffer) >= size:
                yield buffer
                buffer.clear()
        else:
            yield buffer


def evtx2es(filepath: str, host: str = 'localhost', port: int = 9200, index: str = 'evtx2es', type: str = 'evtx2es', size: int = 500):
    es = ElasticsearchUtils(hostname=host, port=port)
    r = Evtx2es(filepath)

    for records in tqdm(r.gen_json(size)):
        try:
            es.bulk_indice(records, index, type)
        except Exception:
            traceback.print_exc()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('evtxfile', help='Windows EVTX file')
    parser.add_argument('--host', default='localhost', help='ElasticSearch host address')
    parser.add_argument('--port', default=9200, help='ElasticSearch port number')
    parser.add_argument('--index', default='evtx2es', help='Index name')
    parser.add_argument('--type', default='evtx2es', help='Document type name')
    parser.add_argument('--size', default=500, help='Bulk insert buffer size')
    args = parser.parse_args()

    evtx2es(
        filepath=args.evtxfile,
        host=args.host,
        port=int(args.port),
        index=args.index,
        type=args.type,
        size=int(args.size)
    )


if __name__ == '__main__':
    main()
