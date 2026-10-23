from datetime import datetime, timedelta
import importlib
import sys

import pytest

from evtx2es.models.Evtx2es import (
    _create_timestamp_field,
    _mp_worker,
    normalize_shift,
    process_by_chunk,
)


def test_shift_keeps_negative_subseconds_and_source_timezone():
    assert _create_timestamp_field(
        "2025-01-02T03:04:05.1234567+02:00",
        timedelta(seconds=-2, microseconds=250000),
    ) == "2025-01-02T01:04:03.3734567Z"


def test_zero_shift_sentinel_is_normalized_at_boundary():
    assert normalize_shift("0") is None
    assert normalize_shift(None) is None
    assert normalize_shift(timedelta(milliseconds=1)) == timedelta(milliseconds=1)
    with pytest.raises(TypeError):
        normalize_shift("1")


def test_serial_and_worker_receive_the_same_raw_timedelta(monkeypatch):
    module = importlib.import_module("evtx2es.models.Evtx2es")
    seen = []
    monkeypatch.setattr(
        module,
        "format_record",
        lambda record, filepath, shift, additional_tags: seen.append(shift) or {},
    )
    shift = timedelta(microseconds=125)

    process_by_chunk([{}], "input.evtx", shift)
    _mp_worker(([{}], "input.evtx", shift, None))

    assert seen == [shift, shift]


def test_datasetdate_is_compared_to_a_fixed_utc_clock(monkeypatch):
    view_module = importlib.import_module("evtx2es.views.ArtifactOptions")
    from evtx2es.views.Evtx2esView import Evtx2esView

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2025, 1, 2, 3, 4, 5, tzinfo=tz)

    monkeypatch.setattr(view_module, "datetime", FixedDateTime)
    monkeypatch.setattr(
        sys,
        "argv",
        ["evtx2es", "input.evtx", "--datasetdate", "01/02/2025.03:04:07"],
    )

    shift, _ = Evtx2esView().get_shift_and_tags()

    assert shift == timedelta(seconds=-2)
