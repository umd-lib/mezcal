import pytest
from requests.auth import HTTPBasicAuth
from requests_jwtauth import HTTPBearerAuth, JWTSecretAuth

from mezcal.http import RepositoryAuthType
from mezcal.web import get_authenticator


def test_get_authenticator_none():
    auth = get_authenticator(RepositoryAuthType.NONE)
    assert auth is None


def test_get_authenticator_basic(monkeypatch):
    monkeypatch.setenv('REPO_USERNAME', 'foo')
    monkeypatch.setenv('REPO_PASSWORD', 'bar')
    auth = get_authenticator(RepositoryAuthType.BASIC)
    assert isinstance(auth, HTTPBasicAuth)
    assert auth.username == 'foo'
    assert auth.password == 'bar'


def test_get_authenticator_jwt_token(monkeypatch):
    monkeypatch.setenv('JWT_TOKEN', 'token')
    auth = get_authenticator(RepositoryAuthType.JWT_TOKEN)
    assert isinstance(auth, HTTPBearerAuth)
    assert auth.token == 'token'


def test_get_authenticator_jwt_secret(monkeypatch):
    monkeypatch.setenv('JWT_SECRET', 'secret')
    auth = get_authenticator(RepositoryAuthType.JWT_SECRET)
    assert isinstance(auth, JWTSecretAuth)
    assert auth.secret == 'secret'
    assert auth.claims['sub'] == 'mezcal'
    assert auth.claims['iss'] == 'fcrepo'
    assert auth.claims['role'] == 'fedoraAdmin'


def test_get_authenticator_missing_env(monkeypatch):
    monkeypatch.delenv('JWT_TOKEN', raising=False)
    with pytest.raises(RuntimeError) as e:
        _auth = get_authenticator(RepositoryAuthType.JWT_TOKEN)
        assert str(e) == "Environment variable 'JWT_TOKEN' is not set"
