import io
import logging
import tempfile
from enum import Enum
from hashlib import md5
from pathlib import Path
from struct import unpack
from threading import current_thread

import boto3
from botocore.exceptions import ClientError
from PIL import Image
from PIL.ImageOps import exif_transpose
from codetiming import Timer
from filelock import FileLock

from mezcal.config import TIMER_LOG_FORMAT

logger = logging.getLogger(__name__)


class DirectoryLayout(Enum):
    BASIC = 1
    MD5_ENCODED = 2
    MD5_ENCODED_PAIRTREE = 3


def _parse_layout(layout: DirectoryLayout | str) -> DirectoryLayout:
    if isinstance(layout, str):
        try:
            return DirectoryLayout[layout.upper()]
        except KeyError as e:
            raise RuntimeError(f'{e} is not a recognized storage layout')
    return layout


SUPPORTED_JPEG_MODES = ('L', 'RGB', 'CMYK')


def process_image(fh) -> io.BytesIO:
    """Open fh as an image, apply EXIF transpose and mode conversion, and return a BytesIO
    containing the resulting JPEG data. Raises RuntimeError if the image cannot be processed."""
    try:
        img = Image.open(fh)

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

        buf = io.BytesIO()
        img.save(buf, format='JPEG')
        buf.seek(0)
        return buf
    except Exception as e:
        logger.error(str(e))
        raise RuntimeError('Unable to create mezzanine copy')


class LocalStorage:
    def __init__(self, storage_dir: Path | str = '', layout: DirectoryLayout | str = DirectoryLayout.BASIC):
        self.storage_dir = Path.cwd() / storage_dir
        self.layout = _parse_layout(layout)

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
                return self.storage_dir / '/'.join(pairtree) / encoded_path

    def get_file(self, repo_path: str) -> 'MezzanineFile':
        return MezzanineFile(self.get_dir(repo_path) / 'image.jpg')


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

    def read(self):
        return open(self.path, 'rb')

    def presigned_url(self, expiry_seconds: int = 3600) -> None:
        """Local files are served directly; no presigned URL is used."""
        return None

    def create(self, fh):
        with Timer(
            name=f'create cached image {self.path} in {current_thread().name}',
            logger=logger.info,
            text=TIMER_LOG_FORMAT
        ):
            buf = process_image(fh)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_bytes(buf.read())

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


class S3Storage:
    def __init__(self, bucket: str, prefix: str = '', layout: DirectoryLayout | str = DirectoryLayout.BASIC):
        self.bucket = bucket
        # normalise prefix: always either empty string or ends with exactly one '/'
        self.prefix = prefix.rstrip('/') + '/' if prefix else ''
        self.layout = _parse_layout(layout)
        self._client = boto3.client('s3')

    def get_key(self, repo_path: str) -> str:
        """Return the S3 object key for the given repository path."""
        match self.layout:
            case DirectoryLayout.BASIC:
                return f'{self.prefix}{repo_path}/image.jpg'
            case DirectoryLayout.MD5_ENCODED:
                encoded_path = md5(str(repo_path).encode()).hexdigest()
                return f'{self.prefix}{encoded_path}/image.jpg'
            case DirectoryLayout.MD5_ENCODED_PAIRTREE:
                encoded_path = md5(str(repo_path).encode()).hexdigest()
                pairtree = [str(encoded_path)[n:n + 2] for n in range(0, 6, 2)]
                return f'{self.prefix}{"/".join(pairtree)}/{encoded_path}/image.jpg'

    def get_file(self, repo_path: str) -> 'S3MezzanineFile':
        return S3MezzanineFile(self._client, self.bucket, self.get_key(repo_path))


class S3MezzanineFile:
    def __init__(self, s3_client, bucket: str, key: str):
        self._client = s3_client
        self._bucket = bucket
        self._key = key
        # store lock files in the system temp directory, keyed by an MD5 of the S3 key,
        # so that advisory locking works without requiring any filesystem on the S3 mount
        self.lock_path = Path(tempfile.gettempdir()) / (md5(key.encode()).hexdigest() + '.lock')

    def __str__(self):
        return f's3://{self._bucket}/{self._key}'

    @property
    def exists(self) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=self._key)
            return True
        except ClientError as e:
            if e.response['Error']['Code'] in ('404', 'NoSuchKey'):
                return False
            raise

    @property
    def lock(self):
        return FileLock(self.lock_path)

    def read(self) -> io.BytesIO:
        response = self._client.get_object(Bucket=self._bucket, Key=self._key)
        return io.BytesIO(response['Body'].read())

    def presigned_url(self, expiry_seconds: int = 3600) -> str:
        """Return a presigned GET URL for this S3 object, valid for expiry_seconds."""
        return self._client.generate_presigned_url(
            'get_object',
            Params={'Bucket': self._bucket, 'Key': self._key},
            ExpiresIn=expiry_seconds,
        )

    def create(self, fh):
        with Timer(
            name=f'create cached image {self} in {current_thread().name}',
            logger=logger.info,
            text=TIMER_LOG_FORMAT
        ):
            buf = process_image(fh)
            self._client.put_object(
                Bucket=self._bucket,
                Key=self._key,
                Body=buf.read(),
                ContentType='image/jpeg',
            )

    def delete(self):
        with Timer(
            name=f'delete cached image {self} in {current_thread().name}',
            logger=logger.info,
            text=TIMER_LOG_FORMAT
        ):
            try:
                self._client.delete_object(Bucket=self._bucket, Key=self._key)
            except ClientError as e:
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
