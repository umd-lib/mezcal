import pytest

from mezcal.http import OriginRepository
from mezcal.storage import LocalStorage
from mezcal.web import create_app


@pytest.fixture()
def test_client(datadir):
    flask_app = create_app(
        origin_repo=OriginRepository(base_url='http://example.org/repo/'),
        local_storage=LocalStorage(storage_dir=datadir),
    )

    # Create a test client using the Flask application configured for testing
    with flask_app.test_client() as testing_client:
        # Establish an application context
        with flask_app.app_context():
            yield testing_client
