import io
import tempfile
from unittest.mock import MagicMock

import PIL.Image
import boto3
import pytest
from filelock import FileLock
from moto import mock_aws

from mezcal.storage import DirectoryLayout, S3MezzanineFile, S3Storage

BUCKET = 'test-bucket'
REGION = 'us-east-1'


@pytest.fixture
def s3(monkeypatch):
    monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'testing')
    monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'testing')
    monkeypatch.setenv('AWS_DEFAULT_REGION', REGION)
    with mock_aws():
        client = boto3.client('s3', region_name=REGION)
        client.create_bucket(Bucket=BUCKET)
        yield client


# --- S3Storage.get_key layout tests ---

@pytest.mark.parametrize(
    ('layout', 'expected'),
    [
        (DirectoryLayout.BASIC, 'bar/1/image.jpg'),
        (DirectoryLayout.MD5_ENCODED, '79693ef14b88881ffa7c1f69787a7f91/image.jpg'),
        (DirectoryLayout.MD5_ENCODED_PAIRTREE, '79/69/3e/79693ef14b88881ffa7c1f69787a7f91/image.jpg'),
    ]
)
def test_get_key(layout, expected):
    storage = S3Storage(bucket=BUCKET, layout=layout)
    assert storage.get_key('bar/1') == expected


@pytest.mark.parametrize(
    ('layout', 'expected'),
    [
        (DirectoryLayout.BASIC, 'images/bar/1/image.jpg'),
        (DirectoryLayout.MD5_ENCODED, 'images/79693ef14b88881ffa7c1f69787a7f91/image.jpg'),
        (DirectoryLayout.MD5_ENCODED_PAIRTREE, 'images/79/69/3e/79693ef14b88881ffa7c1f69787a7f91/image.jpg'),
    ]
)
def test_get_key_with_prefix(layout, expected):
    storage = S3Storage(bucket=BUCKET, prefix='images', layout=layout)
    assert storage.get_key('bar/1') == expected


def test_get_key_prefix_trailing_slash_normalised():
    # a trailing slash in the supplied prefix must not produce a double slash in the key
    storage = S3Storage(bucket=BUCKET, prefix='images/')
    assert storage.get_key('bar/1') == 'images/bar/1/image.jpg'


def test_unknown_directory_layout():
    with pytest.raises(RuntimeError) as e_info:
        S3Storage(bucket=BUCKET, layout='foo')
    assert str(e_info.value) == "'FOO' is not a recognized storage layout"


def test_get_file(s3):
    storage = S3Storage(bucket=BUCKET)
    f = storage.get_file('bar/1')
    assert isinstance(f, S3MezzanineFile)
    assert str(f) == f's3://{BUCKET}/bar/1/image.jpg'


# --- S3MezzanineFile.__str__ and lock ---

def test_str(s3):
    storage = S3Storage(bucket=BUCKET)
    f = storage.get_file('bar/1')
    assert str(f) == f's3://{BUCKET}/bar/1/image.jpg'


def test_lock_path_is_in_tempdir(s3):
    storage = S3Storage(bucket=BUCKET)
    f = storage.get_file('bar/1')
    assert str(f.lock_path).startswith(tempfile.gettempdir())
    assert str(f.lock_path).endswith('.lock')


def test_lock_path_is_deterministic(s3):
    storage = S3Storage(bucket=BUCKET)
    f1 = storage.get_file('bar/1')
    f2 = storage.get_file('bar/1')
    assert f1.lock_path == f2.lock_path


def test_lock_path_differs_for_different_keys(s3):
    storage = S3Storage(bucket=BUCKET)
    f1 = storage.get_file('bar/1')
    f2 = storage.get_file('bar/2')
    assert f1.lock_path != f2.lock_path


def test_lock_returns_filelock(s3):
    storage = S3Storage(bucket=BUCKET)
    f = storage.get_file('bar/1')
    assert isinstance(f.lock, FileLock)


# --- exists ---

def test_exists_false(s3):
    storage = S3Storage(bucket=BUCKET)
    f = storage.get_file('bar/1')
    assert not f.exists


def test_exists_true(s3):
    s3.put_object(Bucket=BUCKET, Key='bar/1/image.jpg', Body=b'data', ContentType='image/jpeg')
    storage = S3Storage(bucket=BUCKET)
    f = storage.get_file('bar/1')
    assert f.exists


# --- create ---

def test_create(s3, tmp_path):
    img = PIL.Image.new('RGB', (10, 10), color='red')
    tif_path = tmp_path / 'test.tif'
    img.save(tif_path)

    storage = S3Storage(bucket=BUCKET)
    f = storage.get_file('bar/1')
    assert not f.exists

    with open(tif_path, 'rb') as fh:
        f.create(fh)

    assert f.exists
    head = s3.head_object(Bucket=BUCKET, Key='bar/1/image.jpg')
    assert head['ContentType'] == 'image/jpeg'


def test_create_failure(s3, monkeypatch):
    mock_image = MagicMock(spec=PIL.Image.Image)
    mock_image.mode = 'RGB'
    mock_image.save = MagicMock(side_effect=RuntimeError('save failed'))
    monkeypatch.setattr(PIL.Image, 'open', lambda *_: mock_image)

    storage = S3Storage(bucket=BUCKET)
    f = storage.get_file('bar/1')
    with pytest.raises(RuntimeError):
        f.create(MagicMock())
    assert not f.exists


# --- delete ---

def test_delete(s3):
    s3.put_object(Bucket=BUCKET, Key='bar/1/image.jpg', Body=b'data', ContentType='image/jpeg')
    storage = S3Storage(bucket=BUCKET)
    f = storage.get_file('bar/1')
    assert f.exists
    f.delete()
    assert not f.exists


def test_delete_non_existent(s3):
    # S3 delete_object is idempotent; deleting a missing key must not raise
    storage = S3Storage(bucket=BUCKET)
    f = storage.get_file('bar/1')
    assert not f.exists
    f.delete()
    assert not f.exists


# --- read ---

def test_read(s3):
    content = b'fake jpeg content'
    s3.put_object(Bucket=BUCKET, Key='bar/1/image.jpg', Body=content, ContentType='image/jpeg')
    storage = S3Storage(bucket=BUCKET)
    f = storage.get_file('bar/1')
    result = f.read()
    assert isinstance(result, io.BytesIO)
    assert result.read() == content


# --- presigned_url ---

def test_presigned_url(s3):
    s3.put_object(Bucket=BUCKET, Key='bar/1/image.jpg', Body=b'data', ContentType='image/jpeg')
    storage = S3Storage(bucket=BUCKET)
    f = storage.get_file('bar/1')
    url = f.presigned_url(expiry_seconds=300)
    assert isinstance(url, str)
    assert url.startswith('https://')
    assert 'bar/1/image.jpg' in url


# --- round-trip ---

def test_create_and_delete(s3, tmp_path):
    img = PIL.Image.new('RGB', (10, 10), color='blue')
    tif_path = tmp_path / 'test.tif'
    img.save(tif_path)

    storage = S3Storage(bucket=BUCKET)
    f = storage.get_file('bar/1')
    assert not f.exists

    with open(tif_path, 'rb') as fh:
        f.create(fh)
    assert f.exists

    f.delete()
    assert not f.exists
