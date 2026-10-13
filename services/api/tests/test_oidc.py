"""OIDC token verification: what is accepted, and every way a token is rejected."""

import base64
import hashlib
import hmac
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from oidc_support import AUDIENCE, ISSUER, FakeIdp

from helixos.auth.oidc import OidcError, OidcVerifier
from helixos.config import OidcSettings


def _settings(**overrides) -> OidcSettings:
    values = dict(
        issuer=ISSUER,
        audience=AUDIENCE,
        jwks_url="https://idp.example.test/jwks.json",
        algorithms=("RS256", "ES256"),
        leeway_seconds=0,
        email_claim="email",
        name_claim="name",
    )
    values.update(overrides)
    return OidcSettings(**values)


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def idp() -> FakeIdp:
    return FakeIdp()


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def verifier(idp, clock) -> OidcVerifier:
    return OidcVerifier(_settings(), fetch=idp.fetch, clock=clock)


def _reason(verifier: OidcVerifier, token: str) -> str:
    with pytest.raises(OidcError) as error:
        verifier.verify(token)
    return error.value.reason


def test_valid_token_returns_claims(verifier, idp) -> None:
    claims = verifier.verify(idp.token("idp|alice"))
    assert claims["sub"] == "idp|alice"
    assert claims["email"] == "alice@example.test"


def test_expired_token_is_rejected(verifier, idp) -> None:
    token = idp.token(exp=int(time.time()) - 5)
    assert _reason(verifier, token) == "expired"


def test_leeway_tolerates_small_clock_skew(idp, clock) -> None:
    lenient = OidcVerifier(_settings(leeway_seconds=30), fetch=idp.fetch, clock=clock)
    lenient.verify(idp.token(exp=int(time.time()) - 5))


@pytest.mark.parametrize(
    ("claim", "value"),
    [("aud", "another-api"), ("iss", "https://evil.example.test/")],
)
def test_wrong_audience_or_issuer_is_rejected(verifier, idp, claim, value) -> None:
    assert _reason(verifier, idp.token(**{claim: value})).startswith("invalid_")


def test_token_without_expiry_is_rejected(verifier, idp) -> None:
    payload = {"iss": ISSUER, "aud": AUDIENCE, "sub": "x"}
    token = jwt.encode(
        payload, idp.keys["key-1"], algorithm="RS256", headers={"kid": "key-1"}
    )
    assert _reason(verifier, token).startswith("invalid_")


def test_signature_from_a_different_key_is_rejected(verifier, idp) -> None:
    attacker = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = idp.token(key=attacker)  # claims the trusted kid, wrong private key
    assert _reason(verifier, forged).startswith("invalid_")


def test_alg_none_is_rejected(verifier) -> None:
    def segment(data: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")

    token = (
        f"{segment({'alg': 'none', 'typ': 'JWT'})}."
        f"{segment({'iss': ISSUER, 'aud': AUDIENCE, 'sub': 'x', 'exp': int(time.time()) + 600})}."
    )
    assert _reason(verifier, token) == "algorithm_not_allowed"


def test_hmac_signed_with_the_public_key_is_rejected(verifier, idp) -> None:
    """Algorithm confusion: HS256 keyed with the published public key.

    Hand-built, because PyJWT itself refuses to create such a token.
    """
    from cryptography.hazmat.primitives import serialization

    public_pem = (
        idp.keys["key-1"]
        .public_key()
        .public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )

    def segment(data: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")

    signing_input = (
        f"{segment({'alg': 'HS256', 'typ': 'JWT', 'kid': 'key-1'})}."
        f"{segment({'iss': ISSUER, 'aud': AUDIENCE, 'sub': 'x', 'exp': int(time.time()) + 600})}"
    )
    mac = hmac.new(public_pem, signing_input.encode(), hashlib.sha256).digest()
    token = f"{signing_input}.{base64.urlsafe_b64encode(mac).decode().rstrip('=')}"
    assert _reason(verifier, token) == "algorithm_not_allowed"


def test_unknown_kid_is_rejected(verifier, idp) -> None:
    other = idp.add_key("rogue")
    token = idp.token(kid="rogue", key=other)
    del idp.keys["rogue"]  # never published
    assert _reason(verifier, token) == "unknown_key"


def test_oversized_and_malformed_tokens_are_rejected(verifier) -> None:
    assert _reason(verifier, "a" * 9000) == "token_too_large"
    assert _reason(verifier, "not-a-jwt") == "malformed"


def test_unknown_kids_cannot_make_us_hammer_the_provider(verifier, idp, clock) -> None:
    verifier.verify(idp.token())  # initial fetch
    before = len(idp.fetches)

    for _ in range(25):
        rogue = idp.add_key("rogue")
        token = idp.token(kid="rogue", key=rogue)
        del idp.keys["rogue"]
        assert _reason(verifier, token) == "unknown_key"
    assert len(idp.fetches) - before <= 1

    clock.now += 31
    token = idp.token(kid="rogue", key=idp.add_key("rogue"))
    del idp.keys["rogue"]
    _reason(verifier, token)
    assert len(idp.fetches) - before <= 2


def test_key_rotation_is_picked_up_after_the_refresh_interval(
    verifier, idp, clock
) -> None:
    verifier.verify(idp.token())
    idp.add_key("key-2")
    token = idp.token(kid="key-2")

    clock.now += 31
    assert verifier.verify(token)["sub"] == "idp|alice"


def test_cached_keys_survive_a_provider_outage(verifier, idp, clock) -> None:
    verifier.verify(idp.token())
    idp.down = True
    clock.now += 4000  # cache expired; refresh will fail
    assert verifier.verify(idp.token())["sub"] == "idp|alice"


def test_provider_outage_with_no_cached_keys_is_reported_as_unavailable(
    idp, clock
) -> None:
    idp.down = True
    verifier = OidcVerifier(_settings(), fetch=idp.fetch, clock=clock)
    with pytest.raises(OidcError) as error:
        verifier.verify(idp.token())
    assert error.value.unavailable


def test_jwks_url_is_discovered_from_the_issuer(idp, clock) -> None:
    verifier = OidcVerifier(_settings(jwks_url=None), fetch=idp.fetch, clock=clock)
    verifier.verify(idp.token())
    assert idp.fetches[0] == "https://idp.example.test/.well-known/openid-configuration"
    assert idp.fetches[1] == "https://idp.example.test/jwks.json"


def test_discovery_document_for_another_issuer_is_refused(idp, clock) -> None:
    other = FakeIdp(issuer="https://other.example.test/")
    verifier = OidcVerifier(
        _settings(jwks_url=None),
        fetch=lambda url: (
            {**idp.fetch(url), "issuer": other.issuer}
            if "well-known" in url
            else idp.fetch(url)
        ),
        clock=clock,
    )
    with pytest.raises(OidcError) as error:
        verifier.verify(idp.token())
    assert error.value.unavailable
