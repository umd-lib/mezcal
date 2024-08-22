from http import HTTPStatus


def test_home_no_param(test_client):
    response = test_client.get('/')
    assert response.status_code == 200
    assert 'text/html' in response.content_type
    assert '<form><label>Repository URL:' in response.text


def test_home_valid_param(test_client):
    response = test_client.get('/?url=http://example.org/repo/foo')
    assert response.status_code == HTTPStatus.FOUND
    assert response.headers['Location'] == '/images/foo'


def test_home_invalid_param(test_client):
    response = test_client.get('/?url=http://bad-example.org/repo/foo')
    assert response.status_code == HTTPStatus.NOT_FOUND
