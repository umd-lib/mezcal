import PIL.Image

from mezcal.web import create_app


def test_max_image_pixels(monkeypatch):
    monkeypatch.setenv('MEZCAL_MAX_IMAGE_PIXELS', '1024')
    app = create_app()
    assert app.config['MAX_IMAGE_PIXELS'] == 1024
    assert PIL.Image.MAX_IMAGE_PIXELS == 1024


def test_max_image_pixels_default(monkeypatch):
    original_max_pixels = PIL.Image.MAX_IMAGE_PIXELS
    monkeypatch.setenv('MEZCAL_MAX_IMAGE_PIXELS', '0')
    app = create_app()
    assert app.config['MAX_IMAGE_PIXELS'] == 0
    assert PIL.Image.MAX_IMAGE_PIXELS == original_max_pixels


def test_max_image_pixels_no_limit(monkeypatch):
    monkeypatch.setenv('MEZCAL_MAX_IMAGE_PIXELS', '-1')
    app = create_app()
    assert app.config['MAX_IMAGE_PIXELS'] == -1
    assert PIL.Image.MAX_IMAGE_PIXELS is None
