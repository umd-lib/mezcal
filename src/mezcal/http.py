import logging
from threading import current_thread

import requests
from codetiming import Timer
from plastron.client import Client

from mezcal.config import TIMER_LOG_FORMAT

logger = logging.getLogger(__name__)


class OriginRepository:
    def __init__(self, client: Client):
        self.client = client

    def get(self, repo_path: str) -> requests.Response:
        with Timer(
            name=f'request origin image {repo_path} in {current_thread().name}',
            logger=logger.info,
            text=TIMER_LOG_FORMAT
        ):
            url = f'{self.client.endpoint.url}{repo_path}'
            response = self.client.get(url, stream=True)
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
