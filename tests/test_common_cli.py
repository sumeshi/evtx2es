"""Behavior shared by the four artifact command lines."""

import importlib
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

PACKAGE = next(
    path.name
    for path in (Path(__file__).resolve().parents[1] / "src").iterdir()
    if (path / "__about__.py").is_file()
)
BaseView = importlib.import_module(f"{PACKAGE}.views.BaseView").BaseView


class View(BaseView):
    def define_options(self):
        pass


def test_common_options_and_tag_parsing():
    view = View()
    view.args = view.parser.parse_args(
        ["--size", "7", "--tags", "one, two,,one", "--quiet"]
    )
    assert view.args.size == 7
    assert view.args.quiet is True
    assert view.parse_tags() == ["one", "two", "one"]
    assert View().parser.parse_args([]).size == 500


@pytest.mark.parametrize("size", ["0", "-1", "abc"])
def test_common_size_validation(size):
    with pytest.raises(SystemExit) as raised:
        View().parser.parse_args(["--size", size])
    assert raised.value.code == 2


def test_multiprocessing_option_follows_artifact_capability():
    view = View()
    if view.supports_multiprocessing:
        assert view.parser.parse_args(["--multiprocess"]).multiprocess is True
    else:
        with pytest.raises(SystemExit) as raised:
            view.parser.parse_args(["--multiprocess"])
        assert raised.value.code == 2


def test_frozen_helper_dispatch_rejects_arbitrary_code(tmp_path):
    marker = tmp_path / "executed"
    command = (
        "from multiprocessing.spawn import spawn_main\n"
        f"open({str(marker)!r}, 'w').close()"
    )
    assert BaseView._dispatch_python_command(command) is False
    assert not marker.exists()


def test_frozen_resource_tracker_dispatch(monkeypatch):
    called = []
    tracker = SimpleNamespace(main=called.append)
    monkeypatch.setattr(importlib, "import_module", lambda name: tracker)
    assert (
        BaseView._dispatch_python_command(
            "from multiprocessing.resource_tracker import main\nmain(3)"
        )
        is True
    )
    assert called == [3]


def test_entry_point_initializes_multiprocessing_before_view(monkeypatch):
    import multiprocessing

    called = []
    monkeypatch.setattr(sys, "argv", [PACKAGE])
    monkeypatch.setattr(
        multiprocessing, "freeze_support", lambda: called.append("freeze")
    )

    class Command:
        def run(self):
            called.append("run")

    BaseView.run_entry_point(Command)
    assert called == ["freeze", "run"]
