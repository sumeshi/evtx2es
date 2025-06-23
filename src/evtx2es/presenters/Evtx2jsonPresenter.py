# coding: utf-8
from datetime import datetime
from itertools import chain
from pathlib import Path
from typing import List, Union

import orjson
from evtx2es.models.Evtx2es import Evtx2es
from tqdm import tqdm


class Evtx2jsonPresenter(object):
    def __init__(
        self,
        input_path: str,
        output_path: str,
        shift: Union[str, datetime] = "0",
        is_quiet: bool = False,
        multiprocess: bool = False,
        chunk_size: int = 500,
        additional_tags: List[str] = None,
    ):
        self.input_path = Path(input_path).resolve()
        self.output_path = (
            Path(output_path)
            if output_path
            else Path(self.input_path).with_suffix(".json")
        )
        self.shift = shift
        self.is_quiet = is_quiet
        self.multiprocess = multiprocess
        self.chunk_size = chunk_size
        self.additional_tags = additional_tags

    def evtx2json(self) -> List[dict]:
        r = Evtx2es(self.input_path)
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

    def export_json(self):
        self.output_path.write_text(
            orjson.dumps(self.evtx2json(), option=orjson.OPT_INDENT_2).decode("utf-8")
        )
