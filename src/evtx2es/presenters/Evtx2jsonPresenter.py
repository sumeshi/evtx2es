# coding: utf-8
from datetime import datetime
from itertools import chain
from pathlib import Path
from typing import List, Union, Optional

import orjson
from evtx2es.models.Evtx2es import Evtx2es
from tqdm import tqdm


class Evtx2jsonPresenter:
    def __init__(
        self,
        input_path: str,
        output_path: str,
        shift: Union[str, datetime] = "0",
        is_quiet: bool = False,
        multiprocess: bool = False,
        chunk_size: int = 500,
        additional_tags: Optional[List[str]] = None,
        output_format: str = "json",
    ):
        if output_format not in ("json", "jsonl", "ndjson"):
            raise ValueError(f"Invalid output format: {output_format}")
        self.output_format = output_format
        self.input_path = Path(input_path).resolve()
        self.output_path = (
            Path(output_path)
            if output_path
            else Path(self.input_path).with_suffix(".json" if output_format == "json" else ".jsonl")
        )
        self.shift = shift
        self.is_quiet = is_quiet
        self.multiprocess = multiprocess
        self.chunk_size = chunk_size
        self.additional_tags = additional_tags

    def evtx2json(self) -> List[dict]:
        r = Evtx2es(self.input_path)
        try:
            generator = (
                r.gen_records(
                    self.shift, self.multiprocess, self.chunk_size, self.additional_tags
                )
                if self.is_quiet
                else tqdm(
                    r.gen_records(
                        self.shift, self.multiprocess, self.chunk_size, self.additional_tags
                    )
                )
            )

            buffer: List[dict] = list(chain.from_iterable(generator))
            return buffer
        finally:
            r.close()

    def export_json(self):
        if self.output_path.resolve() == self.input_path or (
            self.output_path.exists() and self.input_path.exists()
            and self.output_path.samefile(self.input_path)
        ):
            raise ValueError(
                "Input and output must be different files; "
                "they must not refer to the same file."
            )
        if self.output_path.is_symlink():
            raise ValueError("The output path must not be a symbolic link.")
        if self.output_format == "json":
            self.output_path.write_bytes(
                orjson.dumps(self.evtx2json(), option=orjson.OPT_INDENT_2)
            )
            return

        parser = Evtx2es(self.input_path)
        records = None
        try:
            records = parser.gen_records(
                self.shift, self.multiprocess, self.chunk_size, self.additional_tags
            )
            progress = records if self.is_quiet else tqdm(records)
            try:
                with self.output_path.open("wb") as output:
                    for batch in progress:
                        for record in batch:
                            output.write(orjson.dumps(record) + b"\n")
            finally:
                if progress is not records:
                    progress.close()
        finally:
            try:
                if records is not None:
                    records.close()
            finally:
                parser.close()
