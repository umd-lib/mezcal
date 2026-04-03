from requests.auth import HTTPBasicAuth
from requests_jwtauth import HTTPBearerAuth, JWTSecretAuth

from mezcal.web import get_authenticator


def test_get_authenticator_none():
    auth = get_authenticator({})
    assert auth is None


def test_get_authenticator_basic():
    auth = get_authenticator({'FCREPO_USERNAME': 'foo', 'FCREPO_PASSWORD': 'bar'})
    assert isinstance(auth, HTTPBasicAuth)
    assert auth.username == 'foo'
    assert auth.password == 'bar'


def test_get_authenticator_jwt_token():
    auth = get_authenticator({'FCREPO_JWT_TOKEN': 'token'})
    assert isinstance(auth, HTTPBearerAuth)
    assert auth.token == 'token'


def test_get_authenticator_jwt_secret():
    auth = get_authenticator({'FCREPO_JWT_SECRET': 'secret'})
    assert isinstance(auth, JWTSecretAuth)
    assert auth.secret == 'secret'
    assert auth.claims['sub'] == 'mezcal'
    assert auth.claims['iss'] == 'fcrepo'
    assert auth.claims['role'] == 'fedoraAdmin'
