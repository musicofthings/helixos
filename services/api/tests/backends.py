"""Storage backends the ELN tests run against."""

import os

POSTGRES_URL = os.getenv("HELIX_TEST_POSTGRES_URL")

# PostgreSQL is opt-in: CI sets HELIX_TEST_POSTGRES_URL.
ELN_CLIENT_FIXTURES = [
    "memory_client",
    "sqlite_client",
    *(["postgres_client"] if POSTGRES_URL else []),
]
