"""A fake OpenID Connect provider for tests: signs tokens, serves a JWKS."""

import json
import time
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

ISSUER = "https://idp.example.test/"
AUDIENCE = "helixos-api"


class FakeIdp:
    def __init__(self, issuer: str = ISSUER, audience: str = AUDIENCE) -> None:
        self.issuer = issuer
        self.audience = audience
        self.keys: dict[str, Any] = {}
        self.fetches: list[str] = []
        self.down = False
        self.add_key("key-1")

    def add_key(self, kid: str):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.keys[kid] = key
        return key

    def jwks(self) -> dict[str, Any]:
        keys = []
        for kid, private in self.keys.items():
            jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key()))
            keys.append({**jwk, "kid": kid, "use": "sig", "alg": "RS256"})
        return {"keys": keys}

    def fetch(self, url: str) -> dict[str, Any]:
        self.fetches.append(url)
        if self.down:
            raise OSError("identity provider unreachable")
        if url.endswith("/.well-known/openid-configuration"):
            return {
                "issuer": self.issuer,
                "jwks_uri": "https://idp.example.test/jwks.json",
            }
        return self.jwks()

    def token(
        self,
        sub: str = "idp|alice",
        *,
        email: str | None = "alice@example.test",
        email_verified: bool = True,
        name: str | None = None,
        kid: str = "key-1",
        key: Any = None,
        **claims: Any,
    ) -> str:
        now = int(time.time())
        payload: dict[str, Any] = {
            "iss": self.issuer,
            "aud": self.audience,
            "sub": sub,
            "iat": now,
            "exp": now + 600,
            **claims,
        }
        if email is not None:
            payload["email"] = email
            payload["email_verified"] = email_verified
        if name is not None:
            payload["name"] = name
        signing = key if key is not None else self.keys[kid]
        return jwt.encode(payload, signing, algorithm="RS256", headers={"kid": kid})
