import pytest
from PIL import Image
from PIL.ExifTags import Base

from mezcal.storage import MezzanineFile, logger

# NOTE: the test images were created with the red pixel value of (255, 0, 0),
# but that has gotten converted to (254, 0, 0) in the process of saving the
# TIFF files
R = (254, 0, 0)
W = (255, 255, 255)
B = (0, 0, 0)

@pytest.mark.parametrize(
    ('src_filename', 'src_wh', 'orientation', 'expected_wh', 'expected_pixels'),
    [
        #('scpa-075123-0001.jpg', (3337, 2587), 6, (2587, 3337), None),

        # TIFF
        # normal
        ('tif/500x250_orientation_1.tif', (500, 250), 1, (500, 250), (B, W, R, W)),
        # mirror horizontal
        ('tif/500x250_orientation_2.tif', (500, 250), 2, (500, 250), (W, B, W, R)),
        # rotate 180
        ('tif/500x250_orientation_3.tif', (500, 250), 3, (500, 250), (R, W, B, W)),
        # mirror vertical
        ('tif/500x250_orientation_4.tif', (500, 250), 4, (500, 250), (W, R, W, B)),

        # NOTE: TIFF files with EXIF Orientation tags respond with the transposed
        # values for calls to `.width` and `.height`. JPEG files do **not** behave
        # this way.

        # mirror horizontal and rotate 270 CW (90 CCW)
        ('tif/500x250_orientation_5.tif', (250, 500), 5, (250, 500), (B, W, R, W)),
        # rotate 90 CW
        ('tif/500x250_orientation_6.tif', (250, 500), 6, (250, 500), (W, B, W, R)),
        # mirror horizontal and rotate 90 CW
        ('tif/500x250_orientation_7.tif', (250, 500), 7, (250, 500), (R, W, B, W)),
        # rotate 270 CW (90 CCW)
        ('tif/500x250_orientation_8.tif', (250, 500), 8, (250, 500), (W, R, W, B)),

        # JPEG
        # normal
        ('jpg/500x250_orientation_1.jpg', (500, 250), 1, (500, 250), (B, W, R, W)),
        # mirror horizontal
        ('jpg/500x250_orientation_2.jpg', (500, 250), 2, (500, 250), (W, B, W, R)),
        # rotate 180
        ('jpg/500x250_orientation_3.jpg', (500, 250), 3, (500, 250), (R, W, B, W)),
        # mirror vertical
        ('jpg/500x250_orientation_4.jpg', (500, 250), 4, (500, 250), (W, R, W, B)),
        # mirror horizontal and rotate 270 CW (90 CCW)
        ('jpg/500x250_orientation_5.jpg', (500, 250), 5, (250, 500), (B, W, R, W)),
        # rotate 90 CW
        ('jpg/500x250_orientation_6.jpg', (500, 250), 6, (250, 500), (W, B, W, R)),
        # mirror horizontal and rotate 90 CW
        ('jpg/500x250_orientation_7.jpg', (500, 250), 7, (250, 500), (R, W, B, W)),
        # rotate 270 CW (90 CCW)
        ('jpg/500x250_orientation_8.jpg', (500, 250), 8, (250, 500), (W, R, W, B)),
    ]
)
def test_create_mezzanine_file(datadir, src_filename, src_wh, orientation, expected_wh, expected_pixels):
    mez = MezzanineFile(datadir / 'image.jpg')
    with (datadir / src_filename).open(mode='rb') as fh:
        mez.create(fh)

    src_img = Image.open(datadir / src_filename)
    assert len(src_img.getexif()) != 0
    assert src_img.getexif().get(Base.Orientation.value) == orientation
    assert (src_img.width, src_img.height) == src_wh

    mez_img = Image.open(mez.path)
    # the mezzanine JPEG should not have EXIF data
    assert len(mez_img.getexif()) == 0
    assert expected_wh == (mez_img.width, mez_img.height)

    # check the corner pixels of the image in clockwise order,
    # starting with the top-left (0, 0) position
    if expected_pixels:
        assert (
            mez_img.getpixel((0, 0)),
            mez_img.getpixel((mez_img.width - 1, 0)),
            mez_img.getpixel((mez_img.width - 1, mez_img.height - 1)),
            mez_img.getpixel((0, mez_img.height - 1)),
        ) == expected_pixels
