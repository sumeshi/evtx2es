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
    import sys
    import multiprocessing
    
    # Python multiprocessing spawn might pass interpreter flags (-E, -s) before the actual multiprocessing command.
    # Nuitka compiled binaries don't consume these flags automatically, so they fall into sys.argv and crash argparse.
    is_mp = False
    for arg in sys.argv:
        if arg == '--multiprocessing-fork' or 'tracker' in arg or arg == '-c':
            is_mp = True
            break
            
    if is_mp:
        if '-c' in sys.argv:
            idx = sys.argv.index('-c')
            if idx + 1 < len(sys.argv) and 'multiprocessing' in sys.argv[idx + 1]:
                exec(sys.argv[idx + 1])
                sys.exit(0)
        
        for arg in sys.argv:
            if 'resource' in arg or 'semaphore' in arg:
                if 'tracker' in arg:
                    import importlib
                    tracker_module = 'resource_tracker' if 'resource' in arg else 'semaphore_tracker'
                    tracker = importlib.import_module(f'multiprocessing.{tracker_module}')
                    tracker.main(int(sys.argv[-1]))
                    sys.exit(0)
                    
        if '--multiprocessing-fork' in sys.argv:
            idx = sys.argv.index('--multiprocessing-fork')
            sys.argv = [sys.argv[0]] + sys.argv[idx:]
            multiprocessing.freeze_support()
            sys.exit(0)

    multiprocessing.freeze_support()
    Evtx2jsonView().run()


if __name__ == "__main__":
    entry_point()
