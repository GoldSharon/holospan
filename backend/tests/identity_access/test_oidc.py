import json
from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from holospan_api.domains.identity_access.oidc import (
    AuthenticationFailed,
    LoginTransaction,
    LoginTransactionCodec,
    OidcProvider,
    build_authorization_url,
    build_end_session_url,
)


def test_ac11_authorization_url_uses_code_pkce_state_and_nonce() -> None:
    transaction = LoginTransaction.create(now=datetime(2026, 11, 22, tzinfo=UTC))

    url = build_authorization_url(
        authorization_endpoint="https://id.example/authorize",
        client_id="holospan-web",
        redirect_uri="https://app.example/api/v1/identity-access/callback",
        scope="openid profile email",
        transaction=transaction,
    )

    assert "response_type=code" in url
    assert "code_challenge_method=S256" in url
    assert "code_challenge=" in url
    assert f"state={transaction.state}" in url
    assert f"nonce={transaction.nonce}" in url


def test_end_session_url_uses_registered_redirect_and_client_id() -> None:
    url = build_end_session_url(
        end_session_endpoint="https://id.example/logout",
        client_id="holospan-web",
        post_logout_redirect_uri="https://app.example/",
    )

    assert url == (
        "https://id.example/logout?client_id=holospan-web&"
        "post_logout_redirect_uri=https%3A%2F%2Fapp.example%2F"
    )


def test_transaction_cookie_is_encrypted_and_tamper_evident() -> None:
    codec = LoginTransactionCodec("a-development-test-secret-that-is-at-least-32-bytes")
    transaction = LoginTransaction.create(now=datetime(2026, 11, 22, tzinfo=UTC))

    encoded = codec.encode(transaction)
    decoded = codec.decode(encoded, now=datetime(2026, 11, 22, 0, 1, tzinfo=UTC))

    assert decoded == transaction
    assert transaction.code_verifier not in encoded
    with pytest.raises(AuthenticationFailed):
        codec.decode(encoded + "corrupt", now=datetime(2026, 11, 22, 0, 1, tzinfo=UTC))


def test_transaction_cookie_expires_after_five_minutes() -> None:
    codec = LoginTransactionCodec("a-development-test-secret-that-is-at-least-32-bytes")
    now = datetime(2026, 11, 22, tzinfo=UTC)
    encoded = codec.encode(LoginTransaction.create(now=now))

    with pytest.raises(AuthenticationFailed):
        codec.decode(encoded, now=now + timedelta(minutes=6))


async def test_ac1_provider_validates_fixed_issuer_audience_nonce_and_signature() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    public_jwk.update({"kid": "test-key", "use": "sig", "alg": "RS256"})
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        if request.url.path.endswith("openid-configuration"):
            return httpx.Response(
                200,
                json={
                    "issuer": "https://id.example",
                    "authorization_endpoint": "https://id.example/authorize",
                    "token_endpoint": "https://id.example/token",
                    "jwks_uri": "https://id.example/jwks",
                    "end_session_endpoint": "https://id.example/logout",
                },
            )
        return httpx.Response(200, json={"keys": [public_jwk]})

    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "iss": "https://id.example",
            "sub": "subject-1",
            "aud": "holospan-web",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=5)).timestamp()),
            "nonce": "nonce-1",
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key", "typ": "JWT"},
    )
    provider = OidcProvider(
        issuer="https://id.example",
        client_id="holospan-web",
        client_secret=None,
        algorithms=["RS256"],
        cache_seconds=300,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    identity = await provider.validate_id_token(token, nonce="nonce-1")

    assert identity.subject == "subject-1"
    assert requested_urls == [
        "https://id.example/.well-known/openid-configuration",
        "https://id.example/jwks",
    ]
    assert await provider.end_session_url("https://app.example/") == (
        "https://id.example/logout?client_id=holospan-web&"
        "post_logout_redirect_uri=https%3A%2F%2Fapp.example%2F"
    )


async def test_provider_supports_internal_discovery_without_weakening_fixed_issuer() -> None:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(
            200,
            json={
                "issuer": "http://localhost:8082/realms/holospan-local",
                "authorization_endpoint": (
                    "http://localhost:8082/realms/holospan-local/protocol/openid-connect/auth"
                ),
                "token_endpoint": (
                    "http://keycloak:8080/realms/holospan-local/protocol/openid-connect/token"
                ),
                "jwks_uri": (
                    "http://keycloak:8080/realms/holospan-local/protocol/openid-connect/certs"
                ),
            },
        )

    provider = OidcProvider(
        issuer="http://localhost:8082/realms/holospan-local",
        discovery_url=(
            "http://keycloak:8080/realms/holospan-local/.well-known/openid-configuration"
        ),
        client_id="holospan-tenant-web",
        client_secret="local-test-secret",  # noqa: S106
        algorithms=["RS256"],
        cache_seconds=300,
        allow_insecure_http=True,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    metadata = await provider.metadata()

    assert metadata.issuer == "http://localhost:8082/realms/holospan-local"
    assert metadata.token_endpoint.startswith("http://keycloak:8080/")
    assert requested_urls == [
        "http://keycloak:8080/realms/holospan-local/.well-known/openid-configuration"
    ]


async def test_ac2_wrong_audience_returns_generic_authentication_failure() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk.update({"kid": "test-key", "use": "sig", "alg": "RS256"})

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("openid-configuration"):
            return httpx.Response(
                200,
                json={
                    "issuer": "https://id.example",
                    "authorization_endpoint": "https://id.example/authorize",
                    "token_endpoint": "https://id.example/token",
                    "jwks_uri": "https://id.example/jwks",
                },
            )
        return httpx.Response(200, json={"keys": [public_jwk]})

    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "iss": "https://id.example",
            "sub": "subject-1",
            "aud": "another-client",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=5)).timestamp()),
            "nonce": "nonce-1",
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )
    provider = OidcProvider(
        issuer="https://id.example",
        client_id="holospan-web",
        client_secret=None,
        algorithms=["RS256"],
        cache_seconds=300,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(AuthenticationFailed):
        await provider.validate_id_token(token, nonce="nonce-1")
