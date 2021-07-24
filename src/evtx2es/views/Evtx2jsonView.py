# coding: utf-8
from datetime import datetime
from multiprocessing import cpu_count

from evtx2es.views.BaseView import BaseView
from evtx2es.presenters.Evtx2jsonPresenter import Evtx2jsonPresenter


class Evtx2jsonView(BaseView):

    def __init__(self):
        super().__init__()
        self.define_options()
        self.args = self.parser.parse_args()

    def define_options(self):
        self.parser.add_argument("evtx_file", type=str, help="Windows Eventlog file to input.")
        self.parser.add_argument("--output-file", "-o", type=str, default="", help="json file path to output.")
        self.parser.add_argument("--datasetdate", default=None, help="Date of latest record in dataset from TimeCreated record - MM/DD/YYYY.HH:MM:SS")

    def run(self):

        # shift timestamp
        if self.args.datasetdate is not None:
            dataset_date = datetime.strptime(self.args.datasetdate, '%m/%d/%Y.%H:%M:%S')
            shift = datetime.now() - dataset_date
        else:
            shift = '0'

        view = Evtx2jsonView()
        view.log(f"Converting {self.args.evtx_file}.", self.args.quiet)

        if self.args.multiprocess:
            view.log(f"Multi-Process: {cpu_count()}", self.args.quiet)

        Evtx2jsonPresenter(
            input_path=self.args.evtx_file,
            output_path=self.args.output_file,
            shift=shift,
            is_quiet=self.args.quiet,
            multiprocess=self.args.multiprocess,
            chunk_size=int(self.args.size),
        ).export_json()

        view.log("Converted.", self.args.quiet)


def entry_point():
    Evtx2jsonView().run()


if __name__ == "__main__":
    entry_point()
