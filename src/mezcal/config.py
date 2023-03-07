import os
from enum import Enum
from pathlib import Path

from dotenv import load_dotenv


class DirectoryLayout(Enum):
    BASIC = 1
    MD5_ENCODED = 2
    MD5_ENCODED_PAIRTREE = 3


load_dotenv()

JWT_TOKEN = os.environ.get('JWT_TOKEN')
REPO_BASE_URL = os.environ.get('REPO_BASE_URL')
STORAGE_DIR = Path.cwd() / os.environ.get('STORAGE_DIR')
STORAGE_LAYOUT = DirectoryLayout[os.environ.get('DIRECTORY_LAYOUT', 'BASIC').upper()]

TIMER_LOG_FORMAT = 'Time to {name}: {milliseconds:.3f} ms'
LOCK_TIMEOUT = 30
