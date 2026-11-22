"""Object storage and upload service acceptance tests for Iteration 0.24."""

import hashlib
import io

import pytest

from src.db.sqlite_client import Database
from src.repositories.stored_objects import StoredObjectDatabaseRepository
from src.services.context import RequestContext
from src.services.uploads import (
    UploadApplicationService,
    UploadIdempotencyConflict,
    UploadNotFoundError,
    UploadValidationError,
)
from src.storage.contracts import InvalidObjectKeyError, ObjectTooLargeError
from src.storage.local import LocalObjectStore
from src.storage.s3 import S3ObjectStore


def test_local_store_is_atomic_bounded_and_rejects_path_traversal(tmp_path):
    store = LocalObjectStore(tmp_path / "objects")
    content = b"private-resume"
    blob = store.put(
        "users/1/resume/a.txt",
        io.BytesIO(content),
        content_type="text/plain",
        max_bytes=100,
    )

    assert blob.size_bytes == len(content)
    assert blob.sha256 == hashlib.sha256(content).hexdigest()
    assert store.read(blob.key, max_bytes=100) == content
    assert store.exists(blob.key)
    with pytest.raises(InvalidObjectKeyError):
        store.put("../escape.txt", io.BytesIO(b"x"), content_type="text/plain", max_bytes=2)
    with pytest.raises(ObjectTooLargeError):
        store.put("users/1/large.txt", io.BytesIO(b"123"), content_type="text/plain", max_bytes=2)
    assert not store.exists("users/1/large.txt")
    assert not list((tmp_path / "objects").rglob("*.part"))
    store.delete(blob.key)
    assert not store.exists(blob.key)


class _Body:
    def __init__(self, value):
        self.value = value

    def read(self, size):
        return self.value[:size]


class _FakeS3:
    def __init__(self):
        self.objects = {}
        self.last_put = None

    def put_object(self, **kwargs):
        self.last_put = dict(kwargs)
        self.objects[kwargs["Key"]] = kwargs["Body"].read()
        return {"ETag": '"etag-1"'}

    def get_object(self, **kwargs):
        return {"Body": _Body(self.objects[kwargs["Key"]])}

    def head_object(self, **kwargs):
        if kwargs["Key"] not in self.objects:
            raise KeyError(kwargs["Key"])
        return {}

    def delete_object(self, **kwargs):
        self.objects.pop(kwargs["Key"], None)


def test_s3_adapter_streams_private_metadata_and_optional_kms():
    client = _FakeS3()
    store = S3ObjectStore("private-bucket", kms_key_id="kms-key", client=client)
    blob = store.put(
        "users/1/audio/a.mp3",
        io.BytesIO(b"sound"),
        content_type="audio/mpeg",
        max_bytes=100,
    )

    assert blob.etag == "etag-1"
    assert client.last_put["Bucket"] == "private-bucket"
    assert client.last_put["ContentLength"] == 5
    assert client.last_put["Metadata"]["sha256"] == blob.sha256
    assert client.last_put["ServerSideEncryption"] == "aws:kms"
    assert "ACL" not in client.last_put
    assert store.read(blob.key, max_bytes=100) == b"sound"
    assert store.exists(blob.key)
    store.delete(blob.key)
    assert not store.exists(blob.key)


def _service(database, store, user_id=1):
    return UploadApplicationService(
        RequestContext(request_id="req_upload", user_id=user_id, username="owner"),
        store,
        StoredObjectDatabaseRepository(database),
    )


def test_upload_service_is_idempotent_and_owner_scoped(tmp_path):
    database = Database(tmp_path / "metadata.db")
    store = LocalObjectStore(tmp_path / "objects")
    service = _service(database, store)
    first = service.upload(
        kind="resume_source",
        filename="resume.pdf",
        content_type="application/pdf",
        stream=io.BytesIO(b"pdf data"),
        idempotency_key="resume-upload-0001",
    )
    replay = service.upload(
        kind="resume_source",
        filename="resume.pdf",
        content_type="application/pdf",
        stream=io.BytesIO(b"pdf data"),
        idempotency_key="resume-upload-0001",
    )

    assert replay["id"] == first["id"]
    assert replay["replayed"] is True
    assert database.count("stored_objects") == 1
    with pytest.raises(UploadIdempotencyConflict):
        service.upload(
            kind="resume_source",
            filename="resume.pdf",
            content_type="application/pdf",
            stream=io.BytesIO(b"different"),
            idempotency_key="resume-upload-0001",
        )
    with pytest.raises(UploadNotFoundError):
        _service(database, store, user_id=2).get(first["id"])
    with pytest.raises(UploadValidationError):
        service.upload(
            kind="resume_source",
            filename="../resume.pdf",
            content_type="application/pdf",
            stream=io.BytesIO(b"x"),
            idempotency_key="resume-upload-0002",
        )
    database.close()
