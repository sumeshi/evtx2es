# coding: utf-8
import argparse
from abc import ABCMeta, abstractmethod
from datetime import datetime

from evtx2es.__about__ import __version__


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
            help="flag to suppress standard output.",
        )
        self.parser.add_argument(
            "--multiprocess",
            "-m",
            action="store_true",
            help="flag to run multiprocessing.",
        )
        self.parser.add_argument(
            "--size",
            "-s",
            type=int,
            default=500,
            help="size of the chunk to be processed for each process.",
        )
        self.parser.add_argument(
            "--tags",
            default="",
            help="Comma-separated tags to add to each record for identification (e.g., hostname, domain name)",
        )
        self.parser.add_argument(
            "--datasetdate",
            default=None,
            help="Date of latest record in dataset from TimeCreated record - MM/DD/YYYY.HH:MM:SS",
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

    def log(self, message: str, is_quiet: bool):
        if not is_quiet:
            print(message)
