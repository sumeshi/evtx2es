# coding: utf-8
from datetime import datetime
from typing import List, Generator, Union, Callable, Optional
from pathlib import Path

from tqdm import tqdm

from evtx2es.models.Evtx2es import Evtx2es
from evtx2es.models.ElasticsearchUtils import ElasticsearchUtils


class Evtx2esPresenter:

    def __init__(
        self,
        input_path: Path,
        host: str = "localhost",
        port: int = 9200,
        index: str = "evtx2es",
        scheme: str = "http",
        pipeline: str = "",
        shift: Union[str, datetime] = "0",
        login: str = "",
        pwd: str = "",
        is_quiet: bool = False,
        multiprocess: bool = False,
        chunk_size: int = 500,
        additional_tags: Optional[List[str]] = None,
        logger: Optional[Callable[[str, bool], None]] = None,
        verify_certs: bool = True,
        ca_certs: str | None = None,
    ):
        self.input_path = input_path
        self.host = host
        self.port = port
        self.index = index
        self.scheme = scheme
        self.pipeline = pipeline
        self.shift = shift
        self.login = login
        self.pwd = pwd
        self.is_quiet = is_quiet
        self.multiprocess = multiprocess
        self.chunk_size = chunk_size
        self.additional_tags = additional_tags
        self.logger = logger
        self.verify_certs = verify_certs
        self.ca_certs = ca_certs

    def evtx2es(self) -> Generator[List[dict], None, None]:
        r = Evtx2es(self.input_path)
        try:
            for batch in (
                r.gen_records(
                    self.shift, self.multiprocess, self.chunk_size, self.additional_tags
                )
                if self.is_quiet
                else tqdm(
                    r.gen_records(
                        self.shift, self.multiprocess, self.chunk_size, self.additional_tags
                    )
                )
            ):
                yield batch
        finally:
            r.close()

    def bulk_import(self):
        es = ElasticsearchUtils(
            hostname=self.host, port=self.port, scheme=self.scheme,
            login=self.login, pwd=self.pwd, verify_certs=self.verify_certs,
            ca_certs=self.ca_certs,
        )
        chunks = None
        total_success = 0
        batch_count = 0
        try:
            chunks = self.evtx2es()
            for records in chunks:
                success, failed = es.bulk_indice(records, self.index, self.pipeline)
                total_success += success
                batch_count += 1
                if failed:
                    raise RuntimeError(
                        f"Elasticsearch failed to index {len(failed)} document(s)"
                    )
        finally:
            try:
                close = getattr(chunks, "close", None)
                if close is not None:
                    close()
            finally:
                es.close()
        if self.logger:
            self.logger(
                f"Bulk import completed: {batch_count} batches processed",
                self.is_quiet,
            )
            self.logger(f"Successfully indexed: {total_success} documents", self.is_quiet)
