# coding: utf-8
from importlib.metadata import version, PackageNotFoundError


def get_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return ''
