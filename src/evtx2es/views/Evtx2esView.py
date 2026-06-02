# coding: utf-8
from typing import List
from pathlib import Path
from multiprocessing import cpu_count

from evtx2es.views.BaseView import BaseView
from evtx2es.presenters.Evtx2esPresenter import Evtx2esPresenter


class Evtx2esView(BaseView):

    def __init__(self):
        super().__init__()
        self.define_options()
        self.args = self.parser.parse_args()

    def define_options(self):
        self.parser.add_argument(
            "evtx_files",
            nargs="+",
            type=str,
            help="Windows Eventlog files or directories containing them. (Files must have a '.evtx' or '.EVTX' extension)",
        )

        self.parser.add_argument(
            "--host", default="localhost", help="ElasticSearch host"
        )
        self.parser.add_argument(
            "--port", default=9200, help="ElasticSearch port number"
        )
        self.parser.add_argument("--index", default="evtx2es", help="Index name")
        self.parser.add_argument(
            "--scheme", default="http", help="Scheme to use (http, https)"
        )
        self.parser.add_argument(
            "--pipeline", default="", help="Ingest pipeline to use"
        )
        self.parser.add_argument(
            "--login", default="", help="Login to use to connect to Elastic database"
        )
        self.parser.add_argument(
            "--pwd", default="", help="Password associated with the login"
        )
        self.parser.add_argument(
            "--no-verify-certs",
            action="store_true",
            help="Disable TLS certificate verification",
        )

    def __list_evtx_files(self, evtx_files: List[str]) -> List[Path]:
        evtx_path_list: List[Path] = []
        for evtx_file in evtx_files:
            p = Path(evtx_file)
            if p.is_dir():
                evtx_path_list.extend(f for f in p.rglob("*") if f.suffix.lower() == ".evtx")
            else:
                if p.suffix.lower() != ".evtx":
                    print(f"Warning: {evtx_file} is not a .evtx file, skipping.")
                    continue
                if not p.exists():
                    print(f"Warning: {evtx_file} does not exist, skipping.")
                    continue
                evtx_path_list.append(p)

        return evtx_path_list

    def run(self):
        shift, additional_tags = self.get_shift_and_tags()

        evtx_files = self.__list_evtx_files(self.args.evtx_files)

        if self.args.multiprocess:
            self.log(f"Multi-Process: {cpu_count()}", self.args.quiet)

        for evtx_file in evtx_files:
            self.log(f"Currently Importing {evtx_file}.", self.args.quiet)

            Evtx2esPresenter(
                input_path=evtx_file,
                host=self.args.host,
                port=int(self.args.port),
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

        self.log("Import completed.", self.args.quiet)


def entry_point():
    from evtx2es.views.BaseView import BaseView
    BaseView.run_entry_point(Evtx2esView)


if __name__ == "__main__":
    entry_point()
