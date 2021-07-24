# coding: utf-8
from typing import List
from pathlib import Path
from datetime import datetime
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
            help="Windows Eventlog or directories containing them. (filename must be set '.*.evtx', or '.*.EVTX')",
        )

        self.parser.add_argument("--host", default="localhost", help="ElasticSearch host")
        self.parser.add_argument("--port", default=9200, help="ElasticSearch port number")
        self.parser.add_argument("--index", default="evtx2es", help="Index name")
        self.parser.add_argument("--scheme", default="http", help="Scheme to use (http, https)")
        self.parser.add_argument("--pipeline", default="", help="Ingest pipeline to use")
        self.parser.add_argument("--datasetdate", default=None, help="Date of latest record in dataset from TimeCreated record - MM/DD/YYYY.HH:MM:SS")
        self.parser.add_argument("--login", default="", help="Login to use to connect to Elastic database")
        self.parser.add_argument("--pwd", default="", help="Password associated with the login")

    def __list_evtx_files(self, evtx_files: List[str]) -> List[Path]:
        evtx_path_list: List[Path] = list()
        for evtx_file in evtx_files:
            if Path(evtx_file).is_dir():
                evtx_path_list.extend(Path(evtx_file).glob("**/*.evtx"))
                evtx_path_list.extend(Path(evtx_file).glob("**/*.EVTX"))
            else:
                evtx_path_list.append(Path(evtx_file))

        return evtx_path_list

    def run(self):
        if self.args.datasetdate is not None:
            dataset_date = datetime.strptime(self.args.datasetdate, '%m/%d/%Y.%H:%M:%S')
            shift = datetime.now() - dataset_date
        else:
            shift = '0'

        view = Evtx2esView()
        evtx_files = self.__list_evtx_files(self.args.evtx_files)

        if self.args.multiprocess:
            view.log(f"Multi-Process: {cpu_count()}", self.args.quiet)

        for evtx_file in evtx_files:
            view.log(f"Currently Importing {evtx_file}.", self.args.quiet)

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
            ).bulk_import()

        view.log("Import completed.", self.args.quiet)


def entry_point():
    Evtx2esView().run()


if __name__ == "__main__":
    entry_point()
