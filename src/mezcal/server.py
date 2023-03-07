import logging

from waitress import serve

from mezcal import __version__
from mezcal.web import app

logger = logging.getLogger(__name__)


def run():
    server_identity = f'mezcal/{__version__}'
    logger.info(f'Starting {server_identity}')
    serve(app, listen='0.0.0.0:5000', ident=server_identity)
