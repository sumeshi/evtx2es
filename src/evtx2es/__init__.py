# coding: utf-8
from datetime import datetime
from typing import List, Union
from pathlib import Path

from evtx2es.models.Evtx2es import Evtx2es
from evtx2es.presenters.Evtx2esPresenter import Evtx2esPresenter


# for use via python-script!

def evtx2es(
    input_path: str,
    host: str = "localhost",
    port: int = 9200,
    index: str = "evtx2es",
    scheme: str = "http",
    pipeline: str = "",
    shift: str = '0',
    login: str = "",
    pwd: str = "",
    multiprocess: bool = False,
    chunk_size: int = 500
) -> None:
    """Fast import of Windows Eventlog into Elasticsearch.
    Args:
        input_path (str):
            Windows Eventlogs to import into Elasticsearch.

        host (str, optional):
            Elasticsearch host address. Defaults to "localhost".

        port (int, optional):
            Elasticsearch port number. Defaults to 9200.

        index (str, optional):
            Name of the index to create. Defaults to "evtx2es".

        scheme (str, optional):
            Elasticsearch address scheme. Defaults to "http".

        pipeline (str, optional):
            Elasticsearch Ingest Pipeline. Defaults to "".

        shift (str, optional):
            Time shift for dataset. Defaults to "0".

        login (str, optional):
            Elasticsearch login to connect into.

        pwd (str, optional):
            Elasticsearch password associated with the login provided.

        multiprocess (bool, optional):
            Flag to run multiprocessing.

        chunk_size (int, optional):
            Size of the chunk to be processed for each process.
    """

    Evtx2esPresenter(
        input_path=Path(input_path),
        host=host,
        port=int(port),
        index=index,
        scheme=scheme,
        pipeline=pipeline,
        shift=shift,
        login=login,
        pwd=pwd,
        is_quiet=True,
        multiprocess=multiprocess,
        chunk_size=int(chunk_size),
    ).bulk_import()


def evtx2json(input_path: str, shift: Union[str, datetime], multiprocess: bool = False, chunk_size: int = 500) -> List[dict]:
    """Convert Windows Eventlog to List[dict].

    Args:
        input_path (str): Input Eventlog file.
        multiprocess (bool): Flag to run multiprocessing.
        chunk_size (int): Size of the chunk to be processed for each process.

    Note:
        Since the content of the file is loaded into memory at once,
        it requires the same amount of memory as the file to be loaded.
    """
    evtx = Evtx2es(Path(input_path).resolve())
    records: List[dict] = sum(list(evtx.gen_records(multiprocess=multiprocess, chunk_size=chunk_size)), list())

    return records
