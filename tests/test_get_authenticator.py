import pytest
from requests.auth import HTTPBasicAuth
from requests_jwtauth import HTTPBearerAuth, JWTSecretAuth

from mezcal.http import RepositoryAuthType
from mezcal.web import get_authenticator


def test_get_authenticator_none():
    auth = get_authenticator(RepositoryAuthType.NONE, {})
    assert auth is None


def test_get_authenticator_basic():
    auth = get_authenticator(RepositoryAuthType.BASIC, {'REPO_USERNAME': 'foo','REPO_PASSWORD': 'bar'})
    assert isinstance(auth, HTTPBasicAuth)
    assert auth.username == 'foo'
    assert auth.password == 'bar'


def test_get_authenticator_jwt_token():
    auth = get_authenticator(RepositoryAuthType.JWT_TOKEN, {'JWT_TOKEN': 'token'})
    assert isinstance(auth, HTTPBearerAuth)
    assert auth.token == 'token'


def test_get_authenticator_jwt_secret():
    auth = get_authenticator(RepositoryAuthType.JWT_SECRET, {'JWT_SECRET': 'secret'})
    assert isinstance(auth, JWTSecretAuth)
    assert auth.secret == 'secret'
    assert auth.claims['sub'] == 'mezcal'
    assert auth.claims['iss'] == 'fcrepo'
    assert auth.claims['role'] == 'fedoraAdmin'


def test_get_authenticator_missing_key():
    with pytest.raises(RuntimeError) as e:
        _auth = get_authenticator(RepositoryAuthType.JWT_TOKEN, {})
        assert str(e) == "Environment variable 'JWT_TOKEN' is not set"
