import logging
import os

from waitress import serve

from mezcal import __version__
from mezcal.http import OriginRepository
from mezcal.storage import LocalStorage, DirectoryLayout
from mezcal.web import create_app

logger = logging.getLogger(__name__)


def run():
    server_identity = f'mezcal/{__version__}'
    logger.info(f'Starting {server_identity}')
    app = create_app(
        local_storage=LocalStorage(
            storage_dir=os.environ.get('STORAGE_DIR', ''),
            layout=DirectoryLayout[os.environ.get('STORAGE_LAYOUT', 'BASIC').upper()],
        ),
        origin_repo=OriginRepository(os.environ.get('REPO_BASE_URL'))
    )
    serve(app, listen='0.0.0.0:5000', ident=server_identity)
