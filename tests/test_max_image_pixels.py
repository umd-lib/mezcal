from importlib import reload

import PIL.Image

import mezcal.storage


def test_max_image_pixels(monkeypatch):
    monkeypatch.setenv('MAX_IMAGE_PIXELS', '1024')
    reload(PIL.Image)
    reload(mezcal.storage)
    assert mezcal.storage.MAX_IMAGE_PIXELS == 1024
    assert PIL.Image.MAX_IMAGE_PIXELS == 1024


def test_max_image_pixels_default(monkeypatch):
    monkeypatch.setenv('MAX_IMAGE_PIXELS', '0')
    reload(PIL.Image)
    original_max_pixels = PIL.Image.MAX_IMAGE_PIXELS
    reload(mezcal.storage)
    assert mezcal.storage.MAX_IMAGE_PIXELS == 0
    assert PIL.Image.MAX_IMAGE_PIXELS == original_max_pixels


def test_max_image_pixels_no_limit(monkeypatch):
    monkeypatch.setenv('MAX_IMAGE_PIXELS', '-1')
    reload(PIL.Image)
    reload(mezcal.storage)
    assert mezcal.storage.MAX_IMAGE_PIXELS == -1
    assert PIL.Image.MAX_IMAGE_PIXELS is None
