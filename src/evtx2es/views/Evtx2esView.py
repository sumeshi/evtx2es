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

    def __list_evtx_files(self, evtx_files: List[str]) -> List[Path]:
        evtx_path_list: List[Path] = []
        for evtx_file in evtx_files:
            p = Path(evtx_file)
            if p.is_dir():
                evtx_path_list.extend(f for f in p.rglob("*") if f.suffix.lower() == ".evtx")
            else:
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
            ).bulk_import()

        self.log("Import completed.", self.args.quiet)


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
    Evtx2esView().run()


if __name__ == "__main__":
    entry_point()
