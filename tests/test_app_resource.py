from http import HTTPStatus
from unittest.mock import patch

import boto3
import pytest
from filelock import Timeout, FileLock
from moto import mock_aws

from mezcal.http import OriginRepository, NotAnImageError
from mezcal.storage import MezzanineFile
from mezcal.web import create_app

BUCKET = 'test-bucket'


@pytest.fixture()
def test_client_s3(datadir, monkeypatch):
    monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'testing')
    monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'testing')
    monkeypatch.setenv('AWS_DEFAULT_REGION', 'us-east-1')
    monkeypatch.setenv('MEZCAL_REPO_BASE_URL', 'http://example.org/repo/')
    monkeypatch.setenv('MEZCAL_STORAGE_BACKEND', 's3')
    monkeypatch.setenv('MEZCAL_S3_BUCKET', BUCKET)
    with mock_aws():
        boto3.client('s3', region_name='us-east-1').create_bucket(Bucket=BUCKET)
        flask_app = create_app()
        with flask_app.test_client() as client:
            with flask_app.app_context():
                yield client, boto3.client('s3', region_name='us-east-1')


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


# --- S3 backend: presigned URL redirect ---

def test_resource_s3_cached_redirects_to_presigned_url(test_client_s3):
    test_client, s3 = test_client_s3
    s3.put_object(Bucket=BUCKET, Key='foo/image.jpg', Body=b'\xff\xd8\xff', ContentType='image/jpeg')
    response = test_client.get('/images/foo', follow_redirects=False)
    assert response.status_code == HTTPStatus.FOUND
    assert 'foo/image.jpg' in response.headers['Location']


def test_resource_s3_uncached_converts_then_redirects(test_client_s3, datadir):
    test_client, s3 = test_client_s3

    class MockImageResponse:
        @property
        def raw(self):
            return open(datadir / 'foo/image.jpg', mode='rb')

    with patch.object(OriginRepository, 'get', return_value=MockImageResponse()):
        response = test_client.get('/images/bar', follow_redirects=False)
    assert response.status_code == HTTPStatus.FOUND
    assert 'bar/image.jpg' in response.headers['Location']


def test_resource_s3_delete(test_client_s3):
    test_client, s3 = test_client_s3
    s3.put_object(Bucket=BUCKET, Key='foo/image.jpg', Body=b'\xff\xd8\xff', ContentType='image/jpeg')
    response = test_client.delete('/images/foo')
    assert response.status_code == HTTPStatus.NO_CONTENT
