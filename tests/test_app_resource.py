from http import HTTPStatus
from unittest.mock import patch

from filelock import Timeout, FileLock

from mezcal.http import OriginRepository, NotAnImageError
from mezcal.storage import MezzanineFile


def test_resource_not_an_image(test_client):
    with patch.object(OriginRepository, 'get', side_effect=NotAnImageError):
        response = test_client.get('/images/bar')
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'Requested resource is not an image' in response.text


def test_resource_runtime_error(test_client):
    with patch.object(OriginRepository, 'get', side_effect=RuntimeError):
        response = test_client.get('/images/bar')
    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR


def test_resource_lock_timeout(test_client):
    with patch.object(FileLock, 'acquire', side_effect=Timeout('foo')):
        response = test_client.get('/images/foo')
    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert 'Unable to access mezzanine copy' in response.text


def test_resource_successful_is_cached(test_client):
    response = test_client.get('/images/foo')
    assert response.status_code == HTTPStatus.OK
    assert response.content_type == 'image/jpeg'


def test_resource_successful(test_client, datadir):
    class MockImageResponse:
        @property
        def raw(self):
            return open(datadir / 'foo/image.jpg', mode='rb')

    with patch.object(OriginRepository, 'get', return_value=MockImageResponse()):
        response = test_client.get('/images/bar')
    assert response.status_code == HTTPStatus.OK
    assert response.content_type == 'image/jpeg'


def test_resource_delete(test_client):
    response = test_client.delete('/images/foo')
    assert response.status_code == HTTPStatus.NO_CONTENT


def test_resource_delete_runtime_error(test_client):
    with patch.object(MezzanineFile, 'delete', side_effect=RuntimeError('Delete error')):
        response = test_client.delete('/images/foo')
    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert 'Delete error' in response.text


def test_resource_delete_lock_timeout(test_client):
    with patch.object(FileLock, 'acquire', side_effect=Timeout('foo')):
        response = test_client.delete('/images/foo')
    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert 'Unable to access mezzanine copy' in response.text
