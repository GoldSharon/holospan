import asyncio
from io import BytesIO

import urllib3
from minio import Minio
from minio.error import S3Error

from holospan_api.domains.system_context.storage import ObjectStorageUnavailable


class S3CompatibleObjectStorage:
    """MinIO SDK adapter for MinIO and AWS S3-compatible deployments."""

    def __init__(
        self,
        *,
        endpoint: str,
        access_key: str,
        secret_key: str,
        secure: bool,
        region: str,
        connect_timeout_seconds: float,
        read_timeout_seconds: float,
    ) -> None:
        http_client = urllib3.PoolManager(
            timeout=urllib3.Timeout(
                connect=connect_timeout_seconds,
                read=read_timeout_seconds,
            ),
            retries=False,
            maxsize=10,
            cert_reqs="CERT_REQUIRED",
        )
        self._client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
            region=region,
            http_client=http_client,
        )

    async def get_object(
        self,
        *,
        bucket: str,
        object_key: str,
        max_bytes: int,
    ) -> bytes:
        def read() -> bytes:
            response = self._client.get_object(bucket, object_key)
            try:
                data = response.read(max_bytes + 1)
            finally:
                response.close()
                response.release_conn()
            if len(data) > max_bytes:
                raise ValueError("object exceeds the bounded read limit")
            return data

        try:
            return await asyncio.to_thread(read)
        except (S3Error, urllib3.exceptions.HTTPError, OSError, ValueError) as exc:
            raise ObjectStorageUnavailable from exc

    async def put_object(
        self,
        *,
        bucket: str,
        object_key: str,
        data: bytes,
        content_type: str,
        sha256: str,
    ) -> None:
        try:
            await asyncio.to_thread(
                self._client.put_object,
                bucket,
                object_key,
                BytesIO(data),
                len(data),
                content_type=content_type,
                metadata={"sha256": sha256},
            )
        except (S3Error, urllib3.exceptions.HTTPError, OSError, ValueError) as exc:
            raise ObjectStorageUnavailable from exc

    async def delete_object(self, *, bucket: str, object_key: str) -> None:
        try:
            await asyncio.to_thread(self._client.remove_object, bucket, object_key)
        except (S3Error, urllib3.exceptions.HTTPError, OSError, ValueError) as exc:
            raise ObjectStorageUnavailable from exc
