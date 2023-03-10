import logging
from http import HTTPStatus
from threading import current_thread

from codetiming import Timer
from filelock import Timeout
from flask import Flask, send_file, request, url_for, redirect, abort

from mezcal.config import REPO_BASE_URL, TIMER_LOG_FORMAT, LOCK_TIMEOUT
from mezcal.http import OriginResource, NotAnImageError
from mezcal.storage import MezzanineFile

logging.basicConfig(level=logging.DEBUG, format='%(levelname)s:%(name)s:%(threadName)s:%(message)s')
logging.getLogger('PIL').setLevel(logging.INFO)
logging.getLogger('filelock').setLevel(logging.INFO)

app = Flask(__name__)


@app.route('/')
def home():
    if 'url' not in request.args:
        return '<form><label>Repository URL: <input name="url" size="120"/></label><button>Fetch</button></form>'

    url = request.args['url']
    if url.startswith(REPO_BASE_URL):
        repo_path = url[len(REPO_BASE_URL):]
        return redirect(url_for('resource', repo_path=repo_path))
    else:
        app.logger.error(f'URL {url} does not start with {REPO_BASE_URL}')
        abort(HTTPStatus.NOT_FOUND)


@app.route('/images/<path:repo_path>')
def resource(repo_path):
    with Timer(
        name=f'retrieve image {repo_path} in {current_thread().name}',
        logger=app.logger.info,
        text=TIMER_LOG_FORMAT
    ):
        local_file = MezzanineFile(repo_path=repo_path)
        try:
            with local_file.lock.acquire(timeout=LOCK_TIMEOUT):
                if not local_file.exists:
                    app.logger.debug(f'No local copy exists for /{repo_path} (local file path: {local_file})')
                    origin_resource = OriginResource(repo_path)
                    try:
                        response = origin_resource.get()
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
    local_file = MezzanineFile(repo_path=repo_path)

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
