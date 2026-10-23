# coding: utf-8
from hashlib import sha1
from typing import Iterable

import orjson
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

from .ElasticsearchAdapter import ElasticsearchAdapter


class ElasticsearchUtils:
    """Shared connection, identity and bulk transport for artifact documents."""

    def __init__(
        self,
        hostname: str,
        port: int,
        scheme: str,
        login: str,
        pwd: str,
        verify_certs: bool = True,
        ca_certs: str | None = None,
    ) -> None:
        # IPv6 literals need brackets in URLs; retain the client's URL validation.
        if ":" in hostname and not hostname.startswith("["):
            hostname = f"[{hostname}]"
        kwargs = {
            "hosts": [f"{scheme}://{hostname}:{port}"],
            "verify_certs": verify_certs,
        }
        if login:
            kwargs["basic_auth"] = (login, pwd)
        if ca_certs is not None:
            kwargs["ca_certs"] = ca_certs
        self.es = Elasticsearch(**kwargs)
        self._adapter = ElasticsearchAdapter(self.es)

    def close(self) -> None:
        self.es.close()

    def calc_hash(self, record: dict) -> str:
        """Hash the original document, before Elasticsearch-specific changes."""
        return sha1(orjson.dumps(record, option=orjson.OPT_SORT_KEYS)).hexdigest()

    def bulk_indice(
        self, records: Iterable[dict], index_name: str, pipeline: str = ""
    ) -> tuple[int, list]:
        """Stream actions and return successful count and item failures."""

        def actions():
            for record in self._adapter.prepare_records(records, index_name):
                event = {
                    "_id": self.calc_hash(record),
                    "_index": index_name,
                    "_source": self._adapter.prepare_source(record),
                }
                if pipeline:
                    event["pipeline"] = pipeline
                yield event

        try:
            success, failed = bulk(
                self.es, actions(), raise_on_error=False, stats_only=False
            )
            return success, failed
        except Exception as error:
            raise Exception(f"Bulk indexing error: {error}") from error
