import logging
import os
from collections.abc import Mapping
from http import HTTPStatus
from threading import current_thread
from typing import Optional, Any

from PIL import Image
from codetiming import Timer
from filelock import Timeout
from flask import Flask, send_file, request, url_for, redirect, abort
from requests.auth import HTTPBasicAuth, AuthBase
from requests_jwtauth import HTTPBearerAuth, JWTSecretAuth

from mezcal.config import TIMER_LOG_FORMAT
from mezcal.http import OriginRepository, NotAnImageError, RepositoryAuthType
from mezcal.storage import LocalStorage, S3Storage, DirectoryLayout

logging.basicConfig(level=logging.DEBUG, format='%(levelname)s:%(name)s:%(threadName)s:%(message)s')
logging.getLogger('PIL').setLevel(logging.INFO)
logging.getLogger('filelock').setLevel(logging.INFO)

LOCK_TIMEOUT = 30


def get_authenticator(authentication_type: RepositoryAuthType, config: Mapping[str, Any]) -> Optional[AuthBase]:
    """Return a new Requests authenticator as determined by the authentication_type parameter.

    Configuration values for the authenticators, if any, are taken from the given `config`
    mapping. Raises a `RuntimeError` if a required key is not set in `config`."""

    try:
        match authentication_type:
            case RepositoryAuthType.NONE:
                return None
            case RepositoryAuthType.BASIC:
                return HTTPBasicAuth(config['REPO_USERNAME'], config['REPO_PASSWORD'])
            case RepositoryAuthType.JWT_TOKEN:
                return HTTPBearerAuth(config['JWT_TOKEN'])
            case RepositoryAuthType.JWT_SECRET:
                return JWTSecretAuth(
                    secret=config['JWT_SECRET'],
                    claims={
                        'sub': 'mezcal',
                        'iss': 'fcrepo',
                        'role': 'fedoraAdmin',
                    }
                )
    except KeyError as e:
        raise RuntimeError(f'Environment variable {e} is not set') from e


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_prefixed_env('MEZCAL')

    max_image_pixels = int(app.config.get('MAX_IMAGE_PIXELS', 0))
    # set a different max pixel size than the default
    # leave MAX_IMAGE_PIXELS at 0 to use the default
    if max_image_pixels > 0:
        # positive numbers mean set a limit
        Image.MAX_IMAGE_PIXELS = max_image_pixels
    elif max_image_pixels < 0:
        # negative numbers mean no limit
        app.logger.warning('MAX_IMAGE_PIXELS is set to "no limit". Only use with origin images from a trusted source.')
        Image.MAX_IMAGE_PIXELS = None

    layout_name = app.config.get('STORAGE_LAYOUT', 'BASIC').upper()
    backend = app.config.get('STORAGE_BACKEND', 'local').lower()
    presigned_url_expiry = int(app.config.get('S3_PRESIGNED_URL_EXPIRY', 3600))
    if backend == 's3':
        bucket = app.config.get('S3_BUCKET')
        if not bucket:
            raise RuntimeError('MEZCAL_S3_BUCKET must be set when MEZCAL_STORAGE_BACKEND=s3')
        storage = S3Storage(
            bucket=bucket,
            prefix=app.config.get('S3_PREFIX', ''),
            layout=DirectoryLayout[layout_name],
        )
    elif backend == 'local':
        storage = LocalStorage(
            storage_dir=app.config.get('STORAGE_DIR', ''),
            layout=DirectoryLayout[layout_name],
        )
    else:
        raise RuntimeError(f'Unknown MEZCAL_STORAGE_BACKEND: {backend!r}. Must be "local" or "s3"')
    origin_repo = OriginRepository(app.config.get('REPO_BASE_URL'))

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
            cached_file = storage.get_file(repo_path)
            try:
                with cached_file.lock.acquire(timeout=LOCK_TIMEOUT):
                    if not cached_file.exists:
                        app.logger.debug(f'No cached copy exists for /{repo_path} (cached file: {cached_file})')
                        auth_type = RepositoryAuthType[os.environ.get("AUTH_TYPE", "NONE")]
                        try:
                            response = origin_repo.get(repo_path, auth=get_authenticator(auth_type, app.config))
                            cached_file.create(response.raw)
                        except NotAnImageError:
                            abort(HTTPStatus.BAD_REQUEST, description='Requested resource is not an image')
                        except RuntimeError as e:
                            abort(HTTPStatus.INTERNAL_SERVER_ERROR, description=str(e))

                        app.logger.debug(f'Saved {cached_file} for /{repo_path}')

                    app.logger.info(f'Sending file {cached_file} for /{repo_path}')
                    url = cached_file.presigned_url(presigned_url_expiry)
                    if url:
                        return redirect(url)
                    return send_file(cached_file.read(), mimetype='image/jpeg')

            except Timeout:
                app.logger.error(
                    f'Unable to acquire a lock to {cached_file} in {LOCK_TIMEOUT}s (lock path: {cached_file.lock_path})'
                )
                abort(HTTPStatus.INTERNAL_SERVER_ERROR, description='Unable to access mezzanine copy')

    @app.route('/images/<path:repo_path>', methods=['DELETE'])
    def delete_resource(repo_path):
        cached_file = storage.get_file(repo_path)

        try:
            with cached_file.lock.acquire(timeout=LOCK_TIMEOUT):
                try:
                    app.logger.info(f'Removing {cached_file} for /{repo_path}')
                    cached_file.delete()
                except RuntimeError as e:
                    abort(HTTPStatus.INTERNAL_SERVER_ERROR, description=str(e))
        except Timeout:
            app.logger.error(
                f'Unable to acquire a lock to {cached_file} in {LOCK_TIMEOUT}s (lock path: {cached_file.lock_path})'
            )
            abort(HTTPStatus.INTERNAL_SERVER_ERROR, description='Unable to access mezzanine copy')

        return '', HTTPStatus.NO_CONTENT

    return app
