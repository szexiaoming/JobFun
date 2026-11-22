"""S3-compatible object storage adapter."""

from __future__ import annotations

import hashlib
import tempfile
from typing import BinaryIO

from src.storage.contracts import ObjectStorageError, ObjectTooLargeError, StoredBlob
from src.storage.local import _CHUNK_SIZE


class S3ObjectStore:
    def __init__(
        self,
        bucket: str,
        *,
        region: str = "",
        endpoint_url: str = "",
        kms_key_id: str = "",
        client=None,
    ) -> None:
        if not bucket:
            raise ValueError("S3 bucket is required")
        if client is None:
            import boto3

            client = boto3.client(
                "s3",
                region_name=region or None,
                endpoint_url=endpoint_url or None,
            )
        self._client = client
        self._bucket = bucket
        self._kms_key_id = kms_key_id

    def put(
        self,
        key: str,
        stream: BinaryIO,
        *,
        content_type: str,
        max_bytes: int,
    ) -> StoredBlob:
        digest = hashlib.sha256()
        size = 0
        with tempfile.SpooledTemporaryFile(max_size=8 * _CHUNK_SIZE) as body:
            while chunk := stream.read(_CHUNK_SIZE):
                size += len(chunk)
                if size > max_bytes:
                    raise ObjectTooLargeError("Object exceeds the configured size limit")
                digest.update(chunk)
                body.write(chunk)
            body.seek(0)
            arguments = {
                "Bucket": self._bucket,
                "Key": key,
                "Body": body,
                "ContentType": content_type,
                "ContentLength": size,
                "Metadata": {"sha256": digest.hexdigest()},
            }
            if self._kms_key_id:
                arguments.update(
                    ServerSideEncryption="aws:kms",
                    SSEKMSKeyId=self._kms_key_id,
                )
            try:
                response = self._client.put_object(**arguments)
            except Exception as exc:
                raise ObjectStorageError("Object could not be stored") from exc
        return StoredBlob(
            key,
            size,
            digest.hexdigest(),
            content_type,
            str(response.get("ETag", "")).strip('"'),
        )

    def read(self, key: str, *, max_bytes: int) -> bytes:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
            data = response["Body"].read(max_bytes + 1)
        except Exception as exc:
            raise ObjectStorageError("Object could not be read") from exc
        if len(data) > max_bytes:
            raise ObjectTooLargeError("Object exceeds the configured read limit")
        return data

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except Exception:
            return False

    def delete(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
        except Exception as exc:
            raise ObjectStorageError("Object could not be deleted") from exc
