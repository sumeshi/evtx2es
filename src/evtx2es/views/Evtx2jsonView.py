# coding: utf-8
from multiprocessing import cpu_count

from evtx2es.views.BaseView import BaseView
from evtx2es.presenters.Evtx2jsonPresenter import Evtx2jsonPresenter


class Evtx2jsonView(BaseView):

    def __init__(self):
        super().__init__()
        self.define_options()
        self.args = self.parser.parse_args()

    def define_options(self):
        self.parser.add_argument(
            "evtx_file", type=str, help="Windows Eventlog file to input."
        )
        self.parser.add_argument(
            "--output-file",
            "-o",
            type=str,
            default="",
            help="json file path to output.",
        )

    def run(self):
        shift, additional_tags = self.get_shift_and_tags()

        self.log(f"Converting {self.args.evtx_file}.", self.args.quiet)

        if self.args.multiprocess:
            self.log(f"Multi-Process: {cpu_count()}", self.args.quiet)

        Evtx2jsonPresenter(
            input_path=self.args.evtx_file,
            output_path=self.args.output_file,
            shift=shift,
            is_quiet=self.args.quiet,
            multiprocess=self.args.multiprocess,
            chunk_size=int(self.args.size),
            additional_tags=additional_tags,
        ).export_json()

        self.log("Converted.", self.args.quiet)


def entry_point():
    from evtx2es.views.BaseView import BaseView
    BaseView.run_entry_point(Evtx2jsonView)


if __name__ == "__main__":
    entry_point()
