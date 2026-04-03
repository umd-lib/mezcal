import pytest

from mezcal.web import create_app


@pytest.fixture()
def test_client(datadir, monkeypatch):
    monkeypatch.setenv('MEZCAL_FCREPO_ENDPOINT', 'http://example.org/repo')
    monkeypatch.setenv('MEZCAL_STORAGE_DIR', str(datadir))
    flask_app = create_app()

    # Create a test client using the Flask application configured for testing
    with flask_app.test_client() as testing_client:
        # Establish an application context
        with flask_app.app_context():
            yield testing_client
