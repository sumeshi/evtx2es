# coding: utf-8
from typing import Iterable
from hashlib import sha1

from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

import orjson


class ElasticsearchUtils:
    def __init__(
        self, hostname: str, port: int, scheme: str, login: str, pwd: str,
        verify_certs: bool = True, ca_certs: str | None = None,
    ) -> None:
        kwargs = {
            "hosts": [f"{scheme}://{hostname}:{port}"],
            "verify_certs": verify_certs,
        }
        if login:
            kwargs["basic_auth"] = (login, pwd)
        if ca_certs is not None:
            kwargs["ca_certs"] = ca_certs
        self.es = Elasticsearch(**kwargs)

    def close(self) -> None:
        self.es.close()

    def calc_hash(self, record: dict) -> str:
        """Calculate hash value from record.

        Args:
            record (dict): Event Log record.

        Returns:
            str: Hash value
        """
        return sha1(orjson.dumps(record, option=orjson.OPT_SORT_KEYS)).hexdigest()

    def bulk_indice(
        self, records: Iterable[dict], index_name: str, pipeline: str
    ) -> tuple:
        """Bulk indices the documents into Elasticsearch.

        Args:
            records (Iterable[dict]): Records read from Event Log files.
            index_name (str): Target Elasticsearch Index.
            pipeline (str): Target Elasticsearch Ingest Pipeline

        Returns:
            tuple: (success_count, failed_list) - Results of bulk indexing operation
        """

        def actions():
            for record in records:
                event = {
                    "_id": self.calc_hash(record),
                    "_index": index_name,
                    "_source": record,
                }
                if pipeline != "":
                    event["pipeline"] = pipeline
                yield event

        # Perform bulk indexing and return results
        try:
            success, failed = bulk(
                self.es, actions(), raise_on_error=False, stats_only=False
            )
            return (success, failed)
        except Exception as e:
            raise Exception(f"Bulk indexing error: {e}") from e
