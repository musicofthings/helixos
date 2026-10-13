#!/usr/bin/env python3
"""A tiny OpenID Connect provider for local development and tests. NOT for production.

    python scripts/mock_oidc.py --port 9100 --users admin@acme.test,sci@acme.test

Implements discovery, authorization code + PKCE (with a user picker instead of a
password), token, JWKS and logout. Tokens are RS256-signed with a key generated
at startup, so they verify against /jwks.json exactly like a real provider's.
Point the API at it with HELIX_OIDC_ISSUER=http://localhost:9100 and the web
app with NEXT_PUBLIC_OIDC_AUTHORITY=http://localhost:9100.
"""

import argparse
import base64
import hashlib
import html
import json
import secrets
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlsplit

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

KID = "mock-1"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
CODES: dict[str, dict] = {}


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


class Provider(BaseHTTPRequestHandler):
    issuer = ""
    audience = "helixos-api"
    users: list[str] = []
    verified = True

    def log_message(self, fmt, *args):  # quiet
        pass

    # ------------------------------------------------------------------ #
    def _send(
        self, status: int, body: bytes, content_type: str, extra: dict | None = None
    ):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: dict, status: int = 200):
        self._send(status, json.dumps(payload).encode(), "application/json")

    def _redirect(self, location: str):
        self._send(302, b"", "text/plain", {"Location": location})

    def do_OPTIONS(self):
        self._send(204, b"", "text/plain")

    # ------------------------------------------------------------------ #
    def do_GET(self):
        url = urlsplit(self.path)
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.path == "/.well-known/openid-configuration":
            self._json(
                {
                    "issuer": self.issuer,
                    "authorization_endpoint": f"{self.issuer}/authorize",
                    "token_endpoint": f"{self.issuer}/token",
                    "jwks_uri": f"{self.issuer}/jwks.json",
                    "end_session_endpoint": f"{self.issuer}/logout",
                    "response_types_supported": ["code"],
                    "subject_types_supported": ["public"],
                    "id_token_signing_alg_values_supported": ["RS256"],
                    "code_challenge_methods_supported": ["S256"],
                }
            )
        elif url.path == "/jwks.json":
            jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(KEY.public_key()))
            self._json({"keys": [{**jwk, "kid": KID, "use": "sig", "alg": "RS256"}]})
        elif url.path == "/authorize":
            self._authorize(query)
        elif url.path == "/login":
            self._login(query)
        elif url.path == "/logout":
            target = query.get("post_logout_redirect_uri")
            self._redirect(target) if target else self._send(
                200, b"signed out", "text/plain"
            )
        else:
            self._send(404, b"not found", "text/plain")

    def _authorize(self, query: dict):
        if query.get("response_type") != "code" or not query.get("code_challenge"):
            self._send(400, b"code flow with PKCE is required", "text/plain")
            return
        options = "".join(
            f'<li><a href="/login?{html.escape(urlencode({**query, "user": user}))}">{html.escape(user)}</a></li>'
            for user in self.users
        )
        page = (
            "<!doctype html><title>Mock sign-in</title>"
            "<h1>Mock identity provider</h1><p>Sign in as:</p>"
            f"<ul>{options}</ul>"
        )
        self._send(200, page.encode(), "text/html; charset=utf-8")

    def _login(self, query: dict):
        code = secrets.token_urlsafe(24)
        CODES[code] = {
            "user": query["user"],
            "client_id": query.get("client_id"),
            "redirect_uri": query["redirect_uri"],
            "challenge": query["code_challenge"],
            "nonce": query.get("nonce"),
            "scope": query.get("scope", ""),
        }
        params = {"code": code, "state": query.get("state", "")}
        self._redirect(f"{query['redirect_uri']}?{urlencode(params)}")

    # ------------------------------------------------------------------ #
    def do_POST(self):
        if urlsplit(self.path).path != "/token":
            self._send(404, b"not found", "text/plain")
            return
        length = int(self.headers.get("Content-Length", "0"))
        form = {k: v[0] for k, v in parse_qs(self.rfile.read(length).decode()).items()}
        grant = CODES.pop(form.get("code", ""), None)
        if form.get("grant_type") != "authorization_code" or grant is None:
            self._json({"error": "invalid_grant"}, 400)
            return
        digest = b64url(hashlib.sha256(form.get("code_verifier", "").encode()).digest())
        if (
            digest != grant["challenge"]
            or form.get("redirect_uri") != grant["redirect_uri"]
        ):
            self._json(
                {"error": "invalid_grant", "error_description": "PKCE mismatch"}, 400
            )
            return

        now = int(time.time())
        email = grant["user"]
        profile = {
            "sub": f"mock|{email}",
            "email": email,
            "email_verified": self.verified,
            "name": email.split("@")[0].title(),
        }
        base = {"iss": self.issuer, "iat": now, "exp": now + 3600}
        headers = {"kid": KID}
        access = jwt.encode(
            {**base, **profile, "aud": self.audience, "scope": grant["scope"]},
            KEY,
            algorithm="RS256",
            headers=headers,
        )
        ident = jwt.encode(
            {**base, **profile, "aud": grant["client_id"], "nonce": grant["nonce"]},
            KEY,
            algorithm="RS256",
            headers=headers,
        )
        self._json(
            {
                "access_token": access,
                "id_token": ident,
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": grant["scope"],
            }
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--port", type=int, default=9100)
    parser.add_argument("--audience", default="helixos-api")
    parser.add_argument(
        "--users",
        default="admin@acme.test,sci@acme.test,ext@partner.test",
        help="comma-separated emails",
    )
    parser.add_argument(
        "--unverified-email", action="store_true", help="issue email_verified=false"
    )
    args = parser.parse_args()

    Provider.issuer = f"http://localhost:{args.port}"
    Provider.audience = args.audience
    Provider.users = [item.strip() for item in args.users.split(",") if item.strip()]
    Provider.verified = not args.unverified_email
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Provider)
    print(
        f"Mock OIDC provider at {Provider.issuer} (audience {args.audience}); users: {', '.join(Provider.users)}"
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
