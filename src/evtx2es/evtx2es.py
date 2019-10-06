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
            } for record in records]
        )


class Evtx2es(object):
    def __init__(self, filepath: str) -> None:
        self.path = Path(filepath)
        self.parser = PyEvtxParser(self.path.open(mode='rb'))

    def gen_json(self, size: int) -> Generator:
        buffer: List[dict] = []
        for record in self.parser.records_json():
            record['data'] = json.loads(record.get('data'))

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
