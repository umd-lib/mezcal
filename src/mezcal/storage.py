import logging
import os
from enum import Enum
from hashlib import md5
from pathlib import Path
from struct import unpack
from threading import current_thread

from PIL import Image
from PIL.ImageOps import exif_transpose
from codetiming import Timer
from filelock import FileLock

from mezcal.config import TIMER_LOG_FORMAT

logger = logging.getLogger(__name__)
MAX_IMAGE_PIXELS = int(os.environ.get('MAX_IMAGE_PIXELS', 0))


class DirectoryLayout(Enum):
    BASIC = 1
    MD5_ENCODED = 2
    MD5_ENCODED_PAIRTREE = 3


# set a different max pixel size than the default
# leave MAX_IMAGE_PIXELS at 0 to use the default
if MAX_IMAGE_PIXELS > 0:
    # positive numbers mean set a limit
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
elif MAX_IMAGE_PIXELS < 0:
    # negative numbers mean no limit
    logger.warning('MAX_IMAGE_PIXELS is set to "no limit". Only use with origin images from a trusted source.')
    Image.MAX_IMAGE_PIXELS = None


class LocalStorage:
    def __init__(self, storage_dir: Path | str = '', layout: DirectoryLayout | str = DirectoryLayout.BASIC):
        self.storage_dir = Path.cwd() / storage_dir
        if isinstance(layout, str):
            try:
                self.layout = DirectoryLayout[layout.upper()]
            except KeyError as e:
                raise RuntimeError(f'{e} is not a recognized storage layout')
        else:
            self.layout = layout

    def get_dir(self, repo_path: Path | str) -> Path:
        match self.layout:
            case DirectoryLayout.BASIC:
                # same directory structure as the repository
                return self.storage_dir / repo_path
            case DirectoryLayout.MD5_ENCODED:
                # directories named by md5-encoding the repository path
                encoded_path = md5(str(repo_path).encode()).hexdigest()
                return self.storage_dir / encoded_path
            case DirectoryLayout.MD5_ENCODED_PAIRTREE:
                # directories named by md5-encoding the repository path, with pairtree elements
                encoded_path = md5(str(repo_path).encode()).hexdigest()
                pairtree = [str(encoded_path)[n:n + 2] for n in range(0, 6, 2)]
                return self.storage_dir / os.path.join(*pairtree) / encoded_path

    def get_file(self, repo_path: str) -> 'MezzanineFile':
        return MezzanineFile(self.get_dir(repo_path) / 'image.jpg')


SUPPORTED_JPEG_MODES = ('L', 'RGB', 'CMYK')

class MezzanineFile:
    def __init__(self, path: Path = None):
        self.path = path
        self.lock_path = Path(f'{self.path.parent}.lock')

    def __str__(self):
        return str(self.path)

    @property
    def exists(self) -> bool:
        return self.path.exists()

    @property
    def lock(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        return FileLock(self.lock_path)

    def create(self, fh):
        with Timer(
            name=f'create cached image {self.path} in {current_thread().name}',
            logger=logger.info,
            text=TIMER_LOG_FORMAT
        ):
            try:
                img = Image.open(fh)
                self.path.parent.mkdir(parents=True, exist_ok=True)

                exif_transpose(img, in_place=True)

                if img.mode not in SUPPORTED_JPEG_MODES:
                    logger.info(f'Source has mode "{img.mode}" that is not supported by JPEG; will attempt to convert')
                    match img.mode:
                        case 'RGBA' | 'P':
                            # convert to RGB if the source image is RGB-Alpha or Palette
                            logger.debug(f'Converting image from "{img.mode}" to "RGB"')
                            img = img.convert('RGB')
                        case 'I;16':
                            # 16-bit TIFF needs special handling
                            # the point function given scales the 16-bit pixel
                            # values down to 8-bit (which is the max that JPEG
                            # supports) by dividing by 256 (i.e., 2^8)
                            # then the image can be safely rendered as grayscale
                            # (mode "L") JPEG. Without the division by 256,
                            # all the pixel values will likely be over 256,
                            # resulting in an all-white image
                            # see also: https://stackoverflow.com/a/43980135
                            logger.debug(f'Converting image from "{img.mode}" to "L"')
                            img = img.point(lambda i: i / 256).convert('L')
                        case 'I;16B':
                            # 16-bit big endian also needs special handling
                            # in this case we are actually getting the raw bytestream
                            # of the pixel data, unpacking it from big-endian 2-byte
                            # integers, scaling it down from 2-byte to 1-byte pixels,
                            # and creating a new Image object from that data
                            # see also: https://stackoverflow.com/a/26553424
                            logger.debug(f'Converting image from "{img.mode}" to "L"')
                            img = convert_I16B_to_L(img)
                        case _:
                            raise RuntimeError(
                                f'Cannot convert from image mode "{img.mode}" to one of: {SUPPORTED_JPEG_MODES}'
                            )

                img.save(self.path)
            except Exception as e:
                logger.error(str(e))
                raise RuntimeError('Unable to create mezzanine copy')

    def delete(self):
        with Timer(
            name=f'delete cached image {self.path} in {current_thread().name}',
            logger=logger.info,
            text=TIMER_LOG_FORMAT
        ):
            try:
                self.path.unlink(missing_ok=True)
                self.path.parent.rmdir()
            except FileNotFoundError:
                # we can ignore file not found errors, since the whole point
                # of this method is to remove the file and the directory!
                pass
            except Exception as e:
                logger.error(str(e))
                raise RuntimeError('Unable to remove resource')


def convert_I16B_to_L(img: Image) -> Image:
    # format pattern is: big endian marker (">"), followed by
    # the total number pixels (image width * height), followed
    # by the datatype marked for "unsigned short", i.e., 2 bytes
    byte_format = f'>{img.width * img.height}H'
    # unpack the 16-bit big-endian representation of the image pixels
    pixels = unpack(byte_format, img.tobytes())
    # divide by 256 to scale it down to 8-bit
    scaled_pixels = bytes((int(pixel / 256) for pixel in pixels))
    # return a new grayscale (mode "L") image with the converted data
    return Image.frombytes('L', (img.width, img.height), scaled_pixels, 'raw')
