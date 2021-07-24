# coding: utf-8
import traceback
from datetime import datetime
from typing import List, Union
from pathlib import Path

from tqdm import tqdm

from evtx2es.models.Evtx2es import Evtx2es
from evtx2es.models.ElasticsearchUtils import ElasticsearchUtils


class Evtx2esPresenter(object):

    def __init__(
        self,
        input_path: Path,
        host: str = "localhost",
        port: int = 9200,
        index: str = "evtx2es",
        scheme: str = "http",
        pipeline: str = "",
        shift: Union[str, datetime] = '0',
        login: str = "",
        pwd: str = "",
        is_quiet: bool = False,
        multiprocess: bool = False,
        chunk_size: int = 500
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

    def evtx2es(self) -> List[List[dict]]:
        r = Evtx2es(self.input_path)
        generator = r.gen_records(self.shift, self.multiprocess, self.chunk_size) if self.is_quiet else tqdm(r.gen_records(self.shift, self.multiprocess, self.chunk_size))

        buffer: List[List[dict]] = generator
        return buffer

    def bulk_import(self):
        es = ElasticsearchUtils(
            hostname=self.host,
            port=self.port,
            scheme=self.scheme,
            login=self.login,
            pwd=self.pwd
        )

        for records in self.evtx2es():
            try:
                es.bulk_indice(records, self.index, self.pipeline)
            except Exception:
                traceback.print_exc()
