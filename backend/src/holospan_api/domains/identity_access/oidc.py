import base64
import hashlib
import json
import secrets
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
import jwt
from cryptography.fernet import Fernet, InvalidToken
from jwt import PyJWK


class AuthenticationFailed(Exception):
    """Generic authentication failure; callers must not expose the internal cause."""


def _token(length: int = 32) -> str:
    return secrets.token_urlsafe(length)


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


@dataclass(frozen=True, slots=True)
class LoginTransaction:
    state: str
    nonce: str
    code_verifier: str
    created_at: datetime

    @classmethod
    def create(cls, *, now: datetime | None = None) -> "LoginTransaction":
        return cls(
            state=_token(),
            nonce=_token(),
            code_verifier=_token(64),
            created_at=now or datetime.now(UTC),
        )

    @property
    def code_challenge(self) -> str:
        return _pkce_challenge(self.code_verifier)


class LoginTransactionCodec:
    def __init__(self, secret: str, *, lifetime: timedelta = timedelta(minutes=5)) -> None:
        key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
        self._fernet = Fernet(key)
        self._lifetime = lifetime

    def encode(self, transaction: LoginTransaction) -> str:
        payload = asdict(transaction)
        payload["created_at"] = transaction.created_at.isoformat()
        return self._fernet.encrypt(json.dumps(payload).encode()).decode()

    def decode(self, value: str, *, now: datetime | None = None) -> LoginTransaction:
        try:
            raw = base64.b64decode(value.encode(), altchars=b"-_", validate=True)
            if base64.urlsafe_b64encode(raw).decode() != value:
                raise AuthenticationFailed
            payload = json.loads(self._fernet.decrypt(value.encode()).decode())
            transaction = LoginTransaction(
                state=str(payload["state"]),
                nonce=str(payload["nonce"]),
                code_verifier=str(payload["code_verifier"]),
                created_at=datetime.fromisoformat(str(payload["created_at"])),
            )
        except (
            AuthenticationFailed,
            InvalidToken,
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            raise AuthenticationFailed from exc
        current = now or datetime.now(UTC)
        if transaction.created_at.tzinfo is None:
            raise AuthenticationFailed
        if current - transaction.created_at > self._lifetime or current < transaction.created_at:
            raise AuthenticationFailed
        return transaction


def build_authorization_url(
    *,
    authorization_endpoint: str,
    client_id: str,
    redirect_uri: str,
    scope: str,
    transaction: LoginTransaction,
) -> str:
    query = urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "state": transaction.state,
            "nonce": transaction.nonce,
            "code_challenge": transaction.code_challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"{authorization_endpoint}?{query}"


@dataclass(frozen=True, slots=True)
class OidcIdentity:
    issuer: str
    subject: str
    email: str | None
    display_name: str | None
    auth_time: datetime


@dataclass(frozen=True, slots=True)
class OidcMetadata:
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str


class OidcProvider:
    def __init__(
        self,
        *,
        issuer: str,
        client_id: str,
        client_secret: str | None,
        algorithms: list[str],
        cache_seconds: int,
        allow_insecure_http: bool = False,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        normalized = issuer.rstrip("/")
        if not allow_insecure_http and not normalized.startswith("https://"):
            raise ValueError("OIDC issuer must use HTTPS")
        if any(value.lower() == "none" or value.startswith("HS") for value in algorithms):
            raise ValueError("OIDC algorithm allowlist contains an unsafe algorithm")
        self.issuer = normalized
        self.client_id = client_id
        self.client_secret = client_secret
        self.algorithms = algorithms
        self.cache_seconds = cache_seconds
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(5.0))
        self._metadata: tuple[float, OidcMetadata] | None = None
        self._jwks: tuple[float, list[dict[str, object]]] | None = None

    async def metadata(self, *, force: bool = False) -> OidcMetadata:
        now = time.monotonic()
        if not force and self._metadata and self._metadata[0] > now:
            return self._metadata[1]
        try:
            response = await self._client.get(
                f"{self.issuer}/.well-known/openid-configuration",
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            if len(response.content) > 256 * 1024:
                raise AuthenticationFailed
            body = response.json()
            metadata = OidcMetadata(
                issuer=str(body["issuer"]).rstrip("/"),
                authorization_endpoint=str(body["authorization_endpoint"]),
                token_endpoint=str(body["token_endpoint"]),
                jwks_uri=str(body["jwks_uri"]),
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise AuthenticationFailed from exc
        if metadata.issuer != self.issuer:
            raise AuthenticationFailed
        for endpoint in (
            metadata.authorization_endpoint,
            metadata.token_endpoint,
            metadata.jwks_uri,
        ):
            if not endpoint.startswith("https://") and not self.issuer.startswith("http://"):
                raise AuthenticationFailed
        self._metadata = (now + self.cache_seconds, metadata)
        return metadata

    async def _keys(self, *, force: bool = False) -> list[dict[str, object]]:
        now = time.monotonic()
        if not force and self._jwks and self._jwks[0] > now:
            return self._jwks[1]
        metadata = await self.metadata(force=force)
        try:
            response = await self._client.get(
                metadata.jwks_uri,
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            if len(response.content) > 512 * 1024:
                raise AuthenticationFailed
            body = response.json()
            keys = list(body["keys"])
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise AuthenticationFailed from exc
        self._jwks = (now + self.cache_seconds, keys)
        return keys

    async def authorization_endpoint(self) -> str:
        return (await self.metadata()).authorization_endpoint

    async def exchange_code(
        self,
        *,
        code: str,
        redirect_uri: str,
        transaction: LoginTransaction,
    ) -> OidcIdentity:
        metadata = await self.metadata()
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": self.client_id,
            "code_verifier": transaction.code_verifier,
        }
        if self.client_secret:
            form["client_secret"] = self.client_secret
        try:
            response = await self._client.post(metadata.token_endpoint, data=form)
            response.raise_for_status()
            if len(response.content) > 512 * 1024:
                raise AuthenticationFailed
            id_token = str(response.json()["id_token"])
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise AuthenticationFailed from exc
        return await self.validate_id_token(id_token, nonce=transaction.nonce)

    async def validate_id_token(self, token: str, *, nonce: str) -> OidcIdentity:
        try:
            header = jwt.get_unverified_header(token)
            algorithm = str(header["alg"])
            key_id = str(header["kid"])
        except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
            raise AuthenticationFailed from exc
        if algorithm not in self.algorithms or header.get("typ") not in (None, "JWT"):
            raise AuthenticationFailed

        key_data = next((key for key in await self._keys() if key.get("kid") == key_id), None)
        if key_data is None:
            key_data = next(
                (key for key in await self._keys(force=True) if key.get("kid") == key_id),
                None,
            )
        if key_data is None:
            raise AuthenticationFailed
        try:
            key = PyJWK.from_dict(key_data, algorithm=algorithm).key
            claims = jwt.decode(
                token,
                key=key,
                algorithms=self.algorithms,
                audience=self.client_id,
                issuer=self.issuer,
                leeway=30,
                options={"require": ["exp", "iat", "iss", "aud", "sub", "nonce"]},
            )
        except (jwt.PyJWTError, ValueError) as exc:
            raise AuthenticationFailed from exc
        if not secrets.compare_digest(str(claims["nonce"]), nonce):
            raise AuthenticationFailed
        audience = claims["aud"]
        authorized_party = claims.get("azp")
        if authorized_party is not None and authorized_party != self.client_id:
            raise AuthenticationFailed
        if isinstance(audience, list) and len(audience) > 1 and authorized_party != self.client_id:
            raise AuthenticationFailed
        issued_at = datetime.fromtimestamp(int(claims["iat"]), tz=UTC)
        auth_time = datetime.fromtimestamp(int(claims.get("auth_time", claims["iat"])), tz=UTC)
        if auth_time > issued_at + timedelta(seconds=30):
            raise AuthenticationFailed
        return OidcIdentity(
            issuer=str(claims["iss"]).rstrip("/"),
            subject=str(claims["sub"]),
            email=str(claims["email"]) if claims.get("email") else None,
            display_name=str(claims["name"]) if claims.get("name") else None,
            auth_time=auth_time,
        )
