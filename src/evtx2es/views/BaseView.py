# coding: utf-8
import argparse
from abc import ABCMeta, abstractmethod

from evtx2es.models.MetaData import get_version


class BaseView(metaclass=ABCMeta):

    def __init__(self):
        self.parser = argparse.ArgumentParser()
        self.__define_common_options()

    def __define_common_options(self):
        self.parser.add_argument("--version", "-v", action="version", version=get_version('evtx2es'))
        self.parser.add_argument("--quiet", "-q", action='store_true', help="flag to suppress standard output.")
        self.parser.add_argument("--multiprocess", "-m", action='store_true', help="flag to run multiprocessing.")
        self.parser.add_argument("--size", "-s", type=int, default=500, help="size of the chunk to be processed for each process.")
        self.parser.add_argument("--tags", default="", help="Comma-separated tags to add to each record for identification (e.g., hostname, domain name)")

    @abstractmethod
    def define_options(self):
        pass

    def log(self, message: str, is_quiet: bool):
        if not is_quiet:
            print(message)
