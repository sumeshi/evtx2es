# coding: utf-8
from typing import List
import os
from pathlib import Path
from multiprocessing import cpu_count
import stat
import sys

from evtx2es.models.Evtx2es import PartialExtractionError
from evtx2es.presenters.Evtx2esPresenter import InputProcessingError
from evtx2es.views.BaseView import BaseView
from evtx2es.presenters.Evtx2esPresenter import Evtx2esPresenter


class Evtx2esView(BaseView):

    def __init__(self):
        super().__init__()
        self.define_options()
        self.args = self.parser.parse_args()

    def define_options(self):
        self.parser.add_argument(
            "--ca-certs",
            default=None,
            help="Path to a CA certificate bundle for TLS verification.",
        )
        self.parser.add_argument(
            "evtx_files",
            nargs="+",
            type=str,
            help=(
                "Input Windows Event Log files or directories. "
                "Files must have a .evtx extension."
            ),
        )

        self.parser.add_argument(
            "--host", default="localhost", help="Elasticsearch host."
        )
        self.parser.add_argument(
            "--port", default=9200, type=int, help="Elasticsearch port."
        )
        self.parser.add_argument("--index", default="evtx2es", help="Elasticsearch index name.")
        self.parser.add_argument(
            "--scheme", default="http", help="Connection scheme (http or https)."
        )
        self.parser.add_argument(
            "--pipeline", default="", help="Elasticsearch ingest pipeline to use."
        )
        self.parser.add_argument(
            "--login",
            default="",
            help="Username for Elasticsearch authentication.",
        )
        self.parser.add_argument(
            "--pwd",
            default="",
            help="Password for Elasticsearch authentication.",
        )
        self.parser.add_argument(
            "--no-verify-certs",
            action="store_true",
            help="Disable TLS certificate verification.",
        )

    def __list_evtx_files(self, evtx_files: List[str]):
        evtx_path_list: List[Path] = []
        had_invalid_input = False
        for evtx_file in evtx_files:
            p = Path(evtx_file)
            try:
                input_stat = p.stat()
            except OSError as error:
                print(
                    f"Warning: could not read {evtx_file}: {error}; skipping.",
                    file=sys.stderr,
                )
                had_invalid_input = True
                continue

            if stat.S_ISDIR(input_stat.st_mode):
                found = []
                walk_had_error = False

                def onerror(error):
                    nonlocal had_invalid_input
                    nonlocal walk_had_error
                    print(
                        "Warning: could not read "
                        f"{error.filename or evtx_file}: {error}; skipping.",
                        file=sys.stderr,
                    )
                    had_invalid_input = True
                    walk_had_error = True

                for root, _, filenames in os.walk(
                    p, onerror=onerror, followlinks=False
                ):
                    for filename in filenames:
                        if Path(filename).suffix.lower() != ".evtx":
                            continue
                        candidate = Path(root) / filename
                        try:
                            if stat.S_ISREG(candidate.stat().st_mode):
                                found.append(candidate)
                        except OSError as error:
                            onerror(error)
                if not found and not walk_had_error:
                    print(f"Warning: no EVTX files found under {evtx_file}; skipping.", file=sys.stderr)
                    had_invalid_input = True
                evtx_path_list.extend(found)
            else:
                if not stat.S_ISREG(input_stat.st_mode):
                    print(f"Warning: {evtx_file} does not exist or is not a regular file; skipping.", file=sys.stderr)
                    had_invalid_input = True
                    continue
                if p.suffix.lower() != ".evtx":
                    print(f"Warning: {evtx_file} is not an EVTX file; skipping.", file=sys.stderr)
                    had_invalid_input = True
                    continue
                evtx_path_list.append(p)

        unique_paths = []
        seen_paths = set()
        for path in evtx_path_list:
            try:
                resolved_path = path.resolve()
            except OSError as error:
                print(
                    f"Warning: could not read {path}: {error}; skipping.",
                    file=sys.stderr,
                )
                had_invalid_input = True
                continue
            if resolved_path not in seen_paths:
                seen_paths.add(resolved_path)
                unique_paths.append(resolved_path)
        return unique_paths, had_invalid_input

    def run(self):
        shift, additional_tags = self.get_shift_and_tags()

        evtx_files, had_invalid_input = self.__list_evtx_files(self.args.evtx_files)
        if not evtx_files:
            print("Error: no EVTX files found.", file=sys.stderr)
            raise SystemExit(1)

        if self.args.multiprocess:
            self.log(f"Multiprocessing enabled ({cpu_count()} workers).", self.args.quiet)

        for evtx_file in evtx_files:
            self.log(f"Importing {evtx_file}...", self.args.quiet)

            try:
                Evtx2esPresenter(
                    input_path=evtx_file,
                    host=self.args.host,
                    ca_certs=self.args.ca_certs,
                    port=self.args.port,
                    index=self.args.index,
                    scheme=self.args.scheme,
                    pipeline=self.args.pipeline,
                    shift=shift,
                    login=self.args.login,
                    pwd=self.args.pwd,
                    is_quiet=self.args.quiet,
                    multiprocess=self.args.multiprocess,
                    chunk_size=int(self.args.size),
                    additional_tags=additional_tags,
                    logger=self.log,
                    verify_certs=not self.args.no_verify_certs,
                ).bulk_import()
            except (InputProcessingError, PartialExtractionError) as error:
                details = (
                    "; ".join(
                        f"{item['source_file']}: {item['error']}"
                        for item in error.diagnostics
                    )
                    if isinstance(error, PartialExtractionError)
                    else str(error)
                )
                print(f"Warning: failed to process {evtx_file}: {details}", file=sys.stderr)
                had_invalid_input = True

        if had_invalid_input:
            print("Import completed with input failures.", file=sys.stderr)
            raise SystemExit(1)
        self.log("Import completed successfully.", self.args.quiet)


def entry_point():
    from evtx2es.views.BaseView import BaseView
    BaseView.run_entry_point(Evtx2esView)


if __name__ == "__main__":
    entry_point()
