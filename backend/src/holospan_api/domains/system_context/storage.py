from typing import Protocol


class ObjectStorageUnavailable(Exception):
    """Raised when the configured object store cannot complete an operation."""


class ObjectStorage(Protocol):
    async def get_object(
        self,
        *,
        bucket: str,
        object_key: str,
        max_bytes: int,
    ) -> bytes: ...

    async def put_object(
        self,
        *,
        bucket: str,
        object_key: str,
        data: bytes,
        content_type: str,
        sha256: str,
    ) -> None: ...

    async def delete_object(self, *, bucket: str, object_key: str) -> None: ...
