import pytest
from plastron.client import Client
from plastron.client.proxied import ProxiedClient

from mezcal.web import get_client


@pytest.mark.parametrize(
    ('config', 'expected_class'),
    [
        (
            {'FCREPO_ENDPOINT': 'https://example.com/fcrepo/rest'},
            Client,
        ),
        (
            {
                'FCREPO_ENDPOINT': 'https://example.com/fcrepo/rest',
                'FCREPO_ORIGIN': 'http://localhost:8080/fcrepo/rest'
            },
            ProxiedClient,
        ),
    ]
)
def test_get_client(config, expected_class):
    client = get_client(config)
    assert isinstance(client, expected_class)


def test_get_client_missing_config():
    with pytest.raises(RuntimeError):
        get_client({})
