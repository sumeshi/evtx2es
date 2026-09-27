# coding: utf-8
import argparse
from abc import ABCMeta, abstractmethod
from datetime import datetime

from evtx2es.__about__ import __version__


def positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


class BaseView(metaclass=ABCMeta):

    def __init__(self):
        self.parser = argparse.ArgumentParser(allow_abbrev=False)
        self.__define_common_options()

    def __define_common_options(self):
        self.parser.add_argument(
            "--version", "-v", action="version", version=__version__
        )
        self.parser.add_argument(
            "--quiet",
            "-q",
            action="store_true",
            help="Suppress standard output.",
        )
        self.parser.add_argument(
            "--multiprocess",
            "-m",
            action="store_true",
            help="Enable multiprocessing.",
        )
        self.parser.add_argument(
            "--size",
            "-s",
            type=positive_int,
            default=500,
            help="Number of records to process in each chunk.",
        )
        self.parser.add_argument(
            "--tags",
            default="",
            help=(
                "Comma-separated tags to add to each record "
                "(e.g., hostname, domain name)."
            ),
        )
        self.parser.add_argument(
            "--datasetdate",
            default=None,
            help=(
                "Shift timestamps based on the latest record's TimeCreated value "
                "(MM/DD/YYYY.HH:MM:SS)."
            ),
        )

    def get_shift_and_tags(self):
        # shift timestamp
        if getattr(self.args, "datasetdate", None) is not None:
            dataset_date = datetime.strptime(self.args.datasetdate, "%m/%d/%Y.%H:%M:%S")
            shift = datetime.now() - dataset_date
        else:
            shift = "0"

        # Parse tags
        additional_tags = None
        if getattr(self.args, "tags", ""):
            additional_tags = [
                tag.strip() for tag in self.args.tags.split(",") if tag.strip()
            ]

        return shift, additional_tags

    @abstractmethod
    def define_options(self):
        pass

    @staticmethod
    def _dispatch_python_command(command: str) -> bool:
        """Dispatch only known multiprocessing helper commands in frozen builds."""
        import ast
        import importlib

        try:
            tree = ast.parse(command)
        except SyntaxError:
            return False
        if (
            len(tree.body) != 2
            or not isinstance(tree.body[0], ast.ImportFrom)
            or not isinstance(tree.body[1], ast.Expr)
            or not isinstance(tree.body[1].value, ast.Call)
        ):
            return False

        import_node = tree.body[0]
        call = tree.body[1].value
        module = import_node.module
        imported_names = {alias.name for alias in import_node.names}

        if module == "multiprocessing.spawn" and imported_names == {"spawn_main"}:
            if not isinstance(call.func, ast.Name) or call.func.id != "spawn_main":
                return False
            if call.args:
                return False
            try:
                kwargs = {
                    keyword.arg: ast.literal_eval(keyword.value)
                    for keyword in call.keywords
                    if keyword.arg is not None
                }
            except (ValueError, TypeError):
                return False
            from multiprocessing.spawn import spawn_main

            spawn_main(**kwargs)
            return True

        if module in {
            "multiprocessing.resource_tracker",
            "multiprocessing.semaphore_tracker",
        }:
            if imported_names != {"main"}:
                return False
            if not isinstance(call.func, ast.Name) or call.func.id != "main":
                return False
            if len(call.args) != 1 or call.keywords:
                return False
            try:
                fd = ast.literal_eval(call.args[0])
            except (ValueError, TypeError):
                return False
            tracker = importlib.import_module(module)
            tracker.main(fd)
            return True

        return False

    @staticmethod
    def run_entry_point(view_class):
        import multiprocessing
        import sys

        if "-c" in sys.argv:
            idx = sys.argv.index("-c")
            if idx + 1 < len(sys.argv) and BaseView._dispatch_python_command(
                sys.argv[idx + 1]
            ):
                sys.exit(0)

        if "--multiprocessing-fork" in sys.argv:
            idx = sys.argv.index("--multiprocessing-fork")
            sys.argv = [sys.argv[0]] + sys.argv[idx:]
            multiprocessing.freeze_support()
            sys.exit(0)

        multiprocessing.freeze_support()
        view_class().run()

    def log(self, message: str, is_quiet: bool):
        if not is_quiet:
            print(message)
