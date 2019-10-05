# coding: utf-8
import json
import argparse

from pathlib import Path
from typing import NoReturn, List

from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

from evtx import PyEvtxParser
from tqdm import tqdm


class ElasticsearchUtils(object):
    def __init__(self, hostname: str, port: int) -> NoReturn:
        self.es = Elasticsearch(host=hostname, port=port)
    
    def bulk_indice(self, records, index_name: str, type_name: str) -> NoReturn:
        bulk(self.es, [
            {
                '_index': index_name,
                '_type': type_name,
                '_source': record
            } for record in records]
        )


class Evtx2es(object):
    def __init__(self, filepath: str) -> NoReturn:
        self.path = Path(filepath)
        self.parser = PyEvtxParser(self.path.open(mode='rb'))

    def gen_json(self, size: int):
        buffer: List[dict] = []
        for record in self.parser.records_json():
            record['data'] = json.loads(record.get('data'))

            buffer.append(record)
            
            if len(buffer) >= size:
                yield buffer
                buffer.clear()
        else:
            yield buffer


def evtx2es(filepath: str, hostname: str = 'localhost', port: int = 9200, index_name: str = 'evtx2es', type_name: str = 'evtx2es', size: int = 500):
    es = ElasticsearchUtils(hostname=hostname, port=port)
    r = Evtx2es(filepath)

    for records in tqdm(r.gen_json(size)):
        es.bulk_indice(records, index_name, type_name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('evtxfile', help='Windows EVTX file')
    parser.add_argument('--host', default='localhost', help='ElasticSearch host address')
    parser.add_argument('--port', default=9200, help='ElasticSearch port number')
    parser.add_argument('--index', default='evtx2es', help='Index name')
    parser.add_argument('--type', default='evtx2es', help='Type name')
    parser.add_argument('--size', default=500, help='bulk insert size')
    args = parser.parse_args()

    evtx2es(
        filepath=args.evtxfile,
        hostname=args.host,
        port=int(args.port),
        index_name=args.index,
        type_name=args.type,
        size=int(args.size)
    )


if __name__ == '__main__':
    main()