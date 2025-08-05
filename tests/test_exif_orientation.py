import pytest
from PIL import Image
from PIL.ExifTags import Base

from mezcal.storage import MezzanineFile


@pytest.mark.parametrize(
    ('tiff_filename', 'orientation', 'expect_swapped_dimensions'),
    [
        # no Orientation tag
        ('500x250_orientation_None.tif', None, False),
        # normal
        ('500x250_orientation_1.tif', 1, False),
        # mirror horizontal
        ('500x250_orientation_2.tif', 2, False),
        # rotate 180
        ('500x250_orientation_3.tif', 3, False),
        # mirror vertical
        ('500x250_orientation_4.tif', 4, False),
        # mirror horizontal and rotate 270 CW (90 CCW)
        ('500x250_orientation_5.tif', 5, True),
        # rotate 90 CW
        ('500x250_orientation_6.tif', 6, True),
        # mirror horizontal and rotate 90 CW
        ('500x250_orientation_7.tif', 7, True),
        # rotate 270 CW (90 CCW)
        ('500x250_orientation_8.tif', 8, True),
    ]
)
def test_create_mezzanine_file(datadir, tiff_filename, orientation, expect_swapped_dimensions):
    mez = MezzanineFile(datadir / 'image.jpg')
    with (datadir / tiff_filename).open(mode='rb') as fh:
        mez.create(fh)

    tif_img = Image.open(datadir / tiff_filename)
    assert len(tif_img.getexif()) != 0
    assert tif_img.getexif().get(Base.Orientation.value) == orientation

    mez_img = Image.open(mez.path)
    # the mezzanine JPEG should not have EXIF data
    assert len(mez_img.getexif()) == 0
    if expect_swapped_dimensions:
        # because the image was rotated some odd multiple of 90 degrees,
        # the width and height values should be swapped
        assert mez_img.width == tif_img.height
        assert mez_img.height == tif_img.width
    else:
        assert mez_img.width == tif_img.width
        assert mez_img.height == tif_img.height
