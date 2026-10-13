import pytest

from evtx2es.models.Evtx2es import Evtx2es, generate_chunks
from evtx2es.presenters.Evtx2esPresenter import Evtx2esPresenter
from evtx2es.presenters.Evtx2jsonPresenter import Evtx2jsonPresenter


@pytest.mark.parametrize("chunk_size", [0, -1, True, 1.5])
def test_model_helpers_reject_invalid_chunk_sizes(chunk_size):
    with pytest.raises(ValueError, match="greater than zero"):
        list(generate_chunks(chunk_size, []))

    model = object.__new__(Evtx2es)
    with pytest.raises(ValueError, match="greater than zero"):
        list(model.gen_records(None, False, chunk_size))


@pytest.mark.parametrize("presenter", [Evtx2esPresenter, Evtx2jsonPresenter])
@pytest.mark.parametrize("chunk_size", [0, -1])
def test_presenters_reject_invalid_chunk_sizes_before_io(presenter, chunk_size, tmp_path):
    output = tmp_path / "existing.json"
    output.write_bytes(b"sentinel")
    with pytest.raises(ValueError, match="greater than zero"):
        args = (tmp_path / "missing.evtx",) if presenter is Evtx2esPresenter else (
            tmp_path / "missing.evtx", output
        )
        presenter(*args, chunk_size=chunk_size)
    assert output.read_bytes() == b"sentinel"


def test_public_apis_reject_invalid_chunk_sizes_before_opening_input(tmp_path):
    import evtx2es as api

    for convert in (api.evtx2es, api.evtx2json):
        for chunk_size in (0, -1, True, False, 1.5, "2", None):
            with pytest.raises(ValueError, match="greater than zero"):
                convert(str(tmp_path / "missing.evtx"), chunk_size=chunk_size)
