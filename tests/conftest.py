import pytest

from tests.dataset import load_dataset


@pytest.fixture
def dataset() -> dict:
    """A fresh copy of the real story dataset; tests may change it freely."""
    return load_dataset()
