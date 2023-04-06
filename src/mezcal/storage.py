import logging
import os
from enum import Enum
from hashlib import md5
from pathlib import Path
from threading import current_thread

from PIL import Image
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
                # convert to RGB if the source image is RGB-Alpha or Palette
                if img.mode in ('RGBA', 'P'):
                    logger.debug(f'Converting image from "{img.mode}" to "RGB"')
                    img = img.convert('RGB')
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
