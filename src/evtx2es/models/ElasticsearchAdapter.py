"""Artifact adapter: documents need no Elasticsearch-specific conversion."""


class ElasticsearchAdapter:
    def __init__(self, client):
        self.es = client

    def prepare_records(self, records, index_name):
        return records

    def prepare_source(self, record):
        return record
