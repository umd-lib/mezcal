import logging
from collections.abc import Mapping
from http import HTTPStatus
from threading import current_thread
from typing import Any

from PIL import Image
from codetiming import Timer
from filelock import Timeout
from flask import Flask, send_file, request, url_for, redirect, abort
from plastron.client import Client, Endpoint
from plastron.client.proxied import ProxiedClient
from requests.auth import HTTPBasicAuth, AuthBase
from requests_jwtauth import HTTPBearerAuth, JWTSecretAuth

from mezcal.config import TIMER_LOG_FORMAT
from mezcal.http import OriginRepository, NotAnImageError
from mezcal.storage import LocalStorage, DirectoryLayout

logging.basicConfig(level=logging.DEBUG, format='%(levelname)s:%(name)s:%(threadName)s:%(message)s')
logging.getLogger('PIL').setLevel(logging.INFO)
logging.getLogger('filelock').setLevel(logging.INFO)

logger = logging.getLogger(__name__)

LOCK_TIMEOUT = 30


def get_authenticator(config: Mapping[str, Any]) -> AuthBase | None:
    if 'FCREPO_JWT_SECRET' in config:
        return JWTSecretAuth(
            secret=config['FCREPO_JWT_SECRET'],
            claims={'sub': 'mezcal', 'iss': 'fcrepo', 'role': 'fedoraAdmin'},
        )

    if 'FCREPO_JWT_TOKEN' in config:
        return HTTPBearerAuth(config['FCREPO_JWT_TOKEN'])

    if 'FCREPO_USERNAME' in config and 'FCREPO_PASSWORD' in config:
        return HTTPBasicAuth(config['FCREPO_USERNAME'], config['FCREPO_PASSWORD'])

    return None


def get_client(config: Mapping[str, Any]) -> Client:
    try:
        endpoint = Endpoint(config['FCREPO_ENDPOINT'])
        auth = get_authenticator(config)

        if 'FCREPO_ORIGIN' in config:
            return ProxiedClient(
                endpoint=endpoint,
                origin_endpoint=Endpoint(config['FCREPO_ORIGIN']),
                auth=auth,
            )
        else:
            return Client(
                endpoint=endpoint,
                auth=auth,
            )
    except KeyError as e:
        raise RuntimeError(f'Configuration is missing a required key: {e}')


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
    local_storage = LocalStorage(
        storage_dir=app.config.get('STORAGE_DIR', ''),
        layout=DirectoryLayout[layout_name],
    )
    origin_repo = OriginRepository(get_client(app.config))

    @app.route('/')
    def home():
        if 'url' not in request.args:
            return '<form><label>Repository URL: <input name="url" size="120"/></label><button>Fetch</button></form>'

        url = request.args['url']
        endpoint = origin_repo.client.endpoint.url
        if url.startswith(endpoint):
            repo_path = url.removeprefix(endpoint).removeprefix('/')
            return redirect(url_for('resource', repo_path=repo_path))
        else:
            app.logger.error(f'URL {url} does not start with {endpoint}')
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
                        try:
                            response = origin_repo.get(f'/{repo_path}')
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
