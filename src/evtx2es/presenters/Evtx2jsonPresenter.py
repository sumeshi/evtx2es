# coding: utf-8
from datetime import timedelta
from itertools import chain
import os
from pathlib import Path
import stat
from tempfile import NamedTemporaryFile
from typing import List, Union, Optional, Sequence

import orjson
from evtx2es.models.Evtx2es import (
    Evtx2es,
    PartialExtractionError,
    normalize_shift,
    validate_chunk_size,
)
from tqdm import tqdm


class Evtx2jsonPresenter:
    def __init__(
        self,
        input_path: str,
        output_path: str,
        shift: Union[str, timedelta, None] = "0",
        is_quiet: bool = False,
        multiprocess: bool = False,
        chunk_size: int = 500,
        additional_tags: Optional[Union[str, Sequence[str]]] = None,
        output_format: str = "json",
    ):
        validate_chunk_size(chunk_size)
        if output_format not in ("json", "jsonl", "ndjson"):
            raise ValueError(f"Invalid output format: {output_format}")
        self.output_format = output_format
        self.input_path = Path(input_path).resolve()
        self.output_path = (
            Path(output_path)
            if output_path
            else Path(self.input_path).with_suffix(".json" if output_format == "json" else ".jsonl")
        )
        self.shift = normalize_shift(shift)
        self.is_quiet = is_quiet
        self.multiprocess = multiprocess
        self.chunk_size = chunk_size
        self.additional_tags = additional_tags
        self.parse_diagnostics = []

    def evtx2json(self) -> List[dict]:
        r = Evtx2es(self.input_path)
        records = None
        progress = None
        try:
            records = r.gen_records(
                self.shift,
                self.multiprocess,
                self.chunk_size,
                self.additional_tags,
            )
            progress = records if self.is_quiet else tqdm(records)
            buffer: List[dict] = list(chain.from_iterable(progress))
            self.parse_diagnostics = r.diagnostics
            return buffer
        finally:
            try:
                if progress is not None and progress is not records:
                    progress.close()
            finally:
                try:
                    if records is not None:
                        records.close()
                finally:
                    r.close()

    def _check_output_path(self):
        if self.output_path.resolve() == self.input_path or (
            self.output_path.exists()
            and self.input_path.exists()
            and self.output_path.samefile(self.input_path)
        ):
            raise ValueError(
                "Input and output must be different files; "
                "they must not refer to the same file."
            )
        if self.output_path.is_symlink():
            raise ValueError("The output path must not be a symbolic link.")

    def export_json(self):
        self._check_output_path()
        self.parse_diagnostics = []
        temporary_path = None
        parser = None
        records = None
        progress = None
        record_count = 0
        try:
            with NamedTemporaryFile(
                mode="wb",
                dir=self.output_path.parent,
                prefix=f".{self.output_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as output:
                temporary_path = Path(output.name)
                parser = Evtx2es(self.input_path)
                records = parser.gen_records(
                    self.shift,
                    self.multiprocess,
                    self.chunk_size,
                    self.additional_tags,
                )
                progress = records if self.is_quiet else tqdm(records)
                if self.output_format == "json":
                    for batch in progress:
                        for record in batch:
                            output.write(b"[\n" if record_count == 0 else b",\n")
                            # Preserve the full array's indentation while
                            # serializing only one record at a time.
                            output.write(
                                orjson.dumps(
                                    [record], option=orjson.OPT_INDENT_2
                                )[2:-2]
                            )
                            record_count += 1
                        output.flush()
                    output.write(b"\n]" if record_count else b"[]")
                else:
                    for batch in progress:
                        for record in batch:
                            output.write(orjson.dumps(record) + b"\n")
                            record_count += 1
                self.parse_diagnostics = parser.diagnostics
            if self.parse_diagnostics and record_count == 0:
                raise PartialExtractionError(self.parse_diagnostics)
            self._check_output_path()
            if os.name == "posix" and self.output_path.exists():
                temporary_path.chmod(
                    stat.S_IMODE(self.output_path.stat().st_mode)
                )
            os.replace(temporary_path, self.output_path)
            if self.parse_diagnostics:
                raise PartialExtractionError(self.parse_diagnostics)
        finally:
            try:
                try:
                    if progress is not None and progress is not records:
                        progress.close()
                finally:
                    if records is not None:
                        records.close()
            finally:
                try:
                    if parser is not None:
                        parser.close()
                finally:
                    if temporary_path is not None:
                        temporary_path.unlink(missing_ok=True)
