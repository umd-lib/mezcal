import logging
from threading import current_thread

import requests
from codetiming import Timer
from requests.auth import AuthBase

from mezcal.config import REPO_BASE_URL, JWT_TOKEN, TIMER_LOG_FORMAT

logger = logging.getLogger(__name__)


class HTTPBearerAuth(AuthBase):
    def __init__(self, token):
        self.token = token

    def __call__(self, r):
        r.headers['Authorization'] = f'Bearer {self.token}'
        return r


class OriginResource:
    def __init__(self, repo_path: str):
        self.repo_path = repo_path

    def get(self) -> requests.Response:
        with Timer(
            name=f'request origin image {self.repo_path} in {current_thread().name}',
            logger=logger.info,
            text=TIMER_LOG_FORMAT
        ):
            url = REPO_BASE_URL + self.repo_path
            logger.debug(f'Requesting from {url}')
            response = requests.get(url, auth=HTTPBearerAuth(JWT_TOKEN), stream=True)
            if response.ok:
                logger.debug(f'Received {response.status_code} {response.reason} response')
                logger.debug(f'Response headers: {response.headers}')

                # check that we got an image
                content_type = response.headers['Content-Type']
                if not content_type.startswith('image/'):
                    logger.error(f'Resource at {url} is not an image; response Content-Type is "{content_type}"')
                    raise NotAnImageError

                return response
            else:
                logger.error(f'Unable to retrieve {url}: {response.status_code} {response.reason}')
                raise RuntimeError('Unable to retrieve resource')


class NotAnImageError(RuntimeError):
    pass
