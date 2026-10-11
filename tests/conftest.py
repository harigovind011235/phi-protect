import pytest

from phi_protect.composition import Container, create_container
from phi_protect.config.settings import create_settings


@pytest.fixture(scope="session")
def container() -> Container:
    """The real container, with the NER model. Loaded once for the adapter and end-to-end tests."""
    return create_container(create_settings())
