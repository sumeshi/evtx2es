# coding: utf-8
from datetime import timedelta
from typing import List, Union, Sequence
from pathlib import Path
from itertools import chain

from evtx2es.models.Evtx2es import (
    Evtx2es,
    PartialExtractionError,
    normalize_shift,
    validate_chunk_size,
)
from evtx2es.presenters.Evtx2esPresenter import Evtx2esPresenter


# for use via python-script!


def evtx2es(
    input_path: str,
    host: str = "localhost",
    port: int = 9200,
    index: str = "evtx2es",
    scheme: str = "http",
    pipeline: str = "",
    shift: Union[str, timedelta, None] = "0",
    login: str = "",
    pwd: str = "",
    multiprocess: bool = False,
    chunk_size: int = 500,
    additional_tags: Union[str, Sequence[str]] = None,
    verify_certs: bool = True,
) -> None:
    """Fast import of Windows Event Logs into Elasticsearch.
    Args:
        input_path (str):
            Windows Event Logs to import into Elasticsearch.

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

        shift (timedelta or None, optional):
            Timestamp shift. The legacy "0" value is treated as no shift.

        login (str, optional):
            Elasticsearch login to connect into.

        pwd (str, optional):
            Elasticsearch password associated with the login provided.

        multiprocess (bool, optional):
            Flag to run multiprocessing.

        chunk_size (int, optional):
            Size of the chunk to be processed for each process.

        additional_tags (str or Sequence[str], optional):
            Comma-separated string or sequence of tags to add to each record.

        verify_certs (bool, optional):
            Whether to verify TLS certificates for Elasticsearch connections.
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
        chunk_size=chunk_size,
        additional_tags=additional_tags,
        verify_certs=verify_certs,
    ).bulk_import()


def evtx2json(
    input_path: str,
    shift: Union[str, timedelta, None] = "0",
    multiprocess: bool = False,
    chunk_size: int = 500,
    additional_tags: Union[str, Sequence[str]] = None,
) -> List[dict]:
    """Convert a Windows Event Log file to a list of dictionaries.

    Args:
        input_path (str): Input Event Log file.
        shift (timedelta or None): Timestamp shift. Defaults to no shift.
        multiprocess (bool): Flag to run multiprocessing.
        chunk_size (int): Size of the chunk to be processed for each process.
        additional_tags (str or Sequence[str], optional): Comma-separated string
            or sequence of tags to add to each record.

    Note:
        Since the content of the file is loaded into memory at once,
        it requires the same amount of memory as the file to be loaded.
    """
    validate_chunk_size(chunk_size)
    shift = normalize_shift(shift)
    evtx = Evtx2es(Path(input_path).resolve())
    try:
        records: List[dict] = list(
            chain.from_iterable(
                evtx.gen_records(
                    shift=shift,
                    multiprocess=multiprocess,
                    chunk_size=chunk_size,
                    additional_tags=additional_tags,
                )
            )
        )
    finally:
        evtx.close()

    if evtx.diagnostics:
        raise PartialExtractionError(evtx.diagnostics, records)
    return records
