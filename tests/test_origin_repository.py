import pytest
import requests

from mezcal.http import OriginRepository, NotAnImageError


class MockOKResponse:
    ok = True
    status_code = 200
    reason = 'OK'


class NonImageResponse(MockOKResponse):
    headers = {'Content-Type': 'text/plain'}


class ImageResponse(MockOKResponse):
    headers = {'Content-Type': 'image/tiff'}


class MockBadRequestResponse:
    ok = False
    status_code = 400
    reason = 'Bad Request'


def mock_request(response):
    def _request(*_args, **_kwargs):
        return response
    return _request


def test_not_an_image(monkeypatch):
    monkeypatch.setattr(requests, 'get', mock_request(response=NonImageResponse()))
    repo = OriginRepository('http://example.com/repo')
    with pytest.raises(NotAnImageError):
        repo.get('/foo')


def test_image(monkeypatch):
    monkeypatch.setattr(requests, 'get', mock_request(response=ImageResponse()))
    repo = OriginRepository('http://example.com/repo')
    response = repo.get('/foo')
    assert response.ok
    assert response.status_code == 200
    assert response.reason == 'OK'
    assert response.headers['Content-Type'] == 'image/tiff'


def test_origin_not_ok_response(monkeypatch):
    monkeypatch.setattr(requests, 'get', mock_request(response=MockBadRequestResponse()))
    repo = OriginRepository('http://example.com/repo')
    with pytest.raises(RuntimeError) as e:
        repo.get('/foo')
        assert str(e) == 'Unable to retrieve resource'
