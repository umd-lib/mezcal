import logging
import os
from hashlib import md5
from pathlib import Path
from threading import current_thread

from PIL import Image
from codetiming import Timer
from filelock import FileLock

from mezcal.config import STORAGE_DIR, DirectoryLayout, STORAGE_LAYOUT, TIMER_LOG_FORMAT, MAX_IMAGE_PIXELS

logger = logging.getLogger(__name__)

# set a different max pixel size than the default
# leave MAX_IMAGE_PIXELS at 0 to use the default
if MAX_IMAGE_PIXELS > 0:
    # positive numbers mean set a limit
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
elif MAX_IMAGE_PIXELS < 0:
    # negative numbers mean no limit
    logger.warning('MAX_IMAGE_PIXELS is set to "no limit". Only use with origin images from a trusted source.')
    Image.MAX_IMAGE_PIXELS = None


def get_local_dir(repo_path: Path | str, layout: DirectoryLayout = DirectoryLayout.BASIC) -> Path:
    match layout:
        case DirectoryLayout.BASIC:
            # same directory structure as the repository
            return STORAGE_DIR / repo_path
        case DirectoryLayout.MD5_ENCODED:
            # directories named by md5-encoding the repository path
            encoded_path = md5(str(repo_path).encode()).hexdigest()
            return STORAGE_DIR / encoded_path
        case DirectoryLayout.MD5_ENCODED_PAIRTREE:
            # directories named by md5-encoding the repository path, with pairtree elements
            encoded_path = md5(str(repo_path).encode()).hexdigest()
            pairtree = [str(encoded_path)[n:n + 2] for n in range(0, 6, 2)]
            return STORAGE_DIR / os.path.join(*pairtree) / encoded_path


class MezzanineFile:
    def __init__(self, local_path: Path = None, repo_path: str = None):
        if local_path is not None:
            self.path = local_path
        elif repo_path is not None:
            local_dir = get_local_dir(repo_path, STORAGE_LAYOUT)
            self.path = local_dir / 'image.jpg'
        else:
            raise RuntimeError('Must provide one of "local_path" or "repo_path" keyword arguments')

        self.lock_path = self.path.parent / '.image.jpg.lock'

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
