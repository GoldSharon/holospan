import base64
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken


class InvalidCursor(ValueError):
    """Raised when a pagination cursor cannot be authenticated or decoded."""


@dataclass(frozen=True, slots=True)
class CursorPosition:
    created_at: datetime
    item_id: UUID


@dataclass(frozen=True, slots=True)
class RepositoryPage[T]:
    items: list[T]
    next_position: CursorPosition | None


class CursorCodec:
    def __init__(self, secret: str) -> None:
        key = base64.urlsafe_b64encode(
            hashlib.sha256(f"holospan-pagination:{secret}".encode()).digest()
        )
        self._fernet = Fernet(key)

    def encode(self, position: CursorPosition, *, scope: str) -> str:
        if position.created_at.tzinfo is None:
            raise ValueError("cursor timestamps must include a timezone")
        payload = {
            "version": 1,
            "scope": scope,
            "createdAt": position.created_at.isoformat(),
            "itemId": str(position.item_id),
        }
        return self._fernet.encrypt(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        ).decode()

    def decode(self, value: str, *, scope: str) -> CursorPosition:
        try:
            raw = base64.b64decode(value.encode(), altchars=b"-_", validate=True)
            if base64.urlsafe_b64encode(raw).decode() != value:
                raise InvalidCursor
            payload = json.loads(self._fernet.decrypt(value.encode()).decode())
            created_at = datetime.fromisoformat(str(payload["createdAt"]))
            if (
                payload["version"] != 1
                or payload["scope"] != scope
                or created_at.tzinfo is None
            ):
                raise InvalidCursor
            return CursorPosition(
                created_at=created_at,
                item_id=UUID(str(payload["itemId"])),
            )
        except (
            InvalidCursor,
            InvalidToken,
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            raise InvalidCursor from exc
