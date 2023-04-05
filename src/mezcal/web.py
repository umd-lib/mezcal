import logging
import os
from http import HTTPStatus
from threading import current_thread
from typing import Optional

from codetiming import Timer
from filelock import Timeout
from flask import Flask, send_file, request, url_for, redirect, abort
from requests.auth import HTTPBasicAuth, AuthBase
from requests_jwtauth import HTTPBearerAuth, JWTSecretAuth

from mezcal.config import TIMER_LOG_FORMAT
from mezcal.http import OriginRepository, NotAnImageError, RepositoryAuthType
from mezcal.storage import LocalStorage

logging.basicConfig(level=logging.DEBUG, format='%(levelname)s:%(name)s:%(threadName)s:%(message)s')
logging.getLogger('PIL').setLevel(logging.INFO)
logging.getLogger('filelock').setLevel(logging.INFO)

LOCK_TIMEOUT = 30


def get_authenticator(authentication_type: RepositoryAuthType) -> Optional[AuthBase]:
    """Return a new Requests authenticator as determined by the authentication_type parameter.

    Configuration values for the authenticators, if any, are taken from environment variables.
    Raises a RuntimeError if a required environment variable is not set."""

    try:
        match authentication_type:
            case RepositoryAuthType.NONE:
                return None
            case RepositoryAuthType.BASIC:
                return HTTPBasicAuth(os.environ['REPO_USERNAME'], os.environ['REPO_PASSWORD'])
            case RepositoryAuthType.JWT_TOKEN:
                return HTTPBearerAuth(os.environ['JWT_TOKEN'])
            case RepositoryAuthType.JWT_SECRET:
                return JWTSecretAuth(
                    secret=os.environ['JWT_SECRET'],
                    claims={
                        'sub': 'mezcal',
                        'iss': 'fcrepo',
                        'role': 'fedoraAdmin',
                    }
                )
    except KeyError as e:
        raise RuntimeError(f'Environment variable {e} is not set') from e


def create_app(local_storage: LocalStorage, origin_repo: OriginRepository) -> Flask:
    app = Flask(__name__)

    @app.route('/')
    def home():
        if 'url' not in request.args:
            return '<form><label>Repository URL: <input name="url" size="120"/></label><button>Fetch</button></form>'

        url = request.args['url']
        if url.startswith(origin_repo.base_url):
            repo_path = url[len(origin_repo.base_url):]
            return redirect(url_for('resource', repo_path=repo_path))
        else:
            app.logger.error(f'URL {url} does not start with {origin_repo.base_url}')
            abort(HTTPStatus.NOT_FOUND)

    @app.route('/images/<path:repo_path>')
    def resource(repo_path):
        with Timer(
            name=f'retrieve image {repo_path} in {current_thread().name}',
            logger=app.logger.info,
            text=TIMER_LOG_FORMAT
        ):
            local_file = local_storage.get_file(repo_path)
            try:
                with local_file.lock.acquire(timeout=LOCK_TIMEOUT):
                    if not local_file.exists:
                        app.logger.debug(f'No local copy exists for /{repo_path} (local file path: {local_file})')
                        auth_type = RepositoryAuthType[os.environ.get("AUTH_TYPE", "NONE")]
                        try:
                            response = origin_repo.get(repo_path, auth=get_authenticator(auth_type))
                            local_file.create(response.raw)
                        except NotAnImageError:
                            abort(HTTPStatus.BAD_REQUEST, description='Requested resource is not an image')
                        except RuntimeError as e:
                            abort(HTTPStatus.INTERNAL_SERVER_ERROR, description=str(e))

                        app.logger.debug(f'Saved {local_file} for /{repo_path}')

                    app.logger.info(f'Sending file {local_file} for /{repo_path}')
                    return send_file(local_file.path, mimetype='image/jpeg')

            except Timeout:
                app.logger.error(
                    f'Unable to acquire a lock to {local_file} in {LOCK_TIMEOUT}s (lock path: {local_file.lock_path})'
                )
                abort(HTTPStatus.INTERNAL_SERVER_ERROR, description='Unable to access mezzanine copy')

    @app.route('/images/<path:repo_path>', methods=['DELETE'])
    def delete_resource(repo_path):
        local_file = local_storage.get_file(repo_path)

        try:
            with local_file.lock.acquire(timeout=LOCK_TIMEOUT):
                try:
                    app.logger.info(f'Removing {local_file} for /{repo_path}')
                    local_file.delete()
                except RuntimeError as e:
                    abort(HTTPStatus.INTERNAL_SERVER_ERROR, description=str(e))
        except Timeout:
            app.logger.error(
                f'Unable to acquire a lock to {local_file} in {LOCK_TIMEOUT}s (lock path: {local_file.lock_path})'
            )
            abort(HTTPStatus.INTERNAL_SERVER_ERROR, description='Unable to access mezzanine copy')

        return '', HTTPStatus.NO_CONTENT

    return app
