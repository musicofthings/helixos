#!/usr/bin/env python3
"""Desktop sidecar entrypoint for PyInstaller bundles."""

from __future__ import annotations

import os
import sys


def main() -> None:
    import uvicorn

    port = int(os.getenv("HELIX_API_PORT", sys.argv[1] if len(sys.argv) > 1 else "8765"))
    uvicorn.run(
        "helixos.main:app",
        host="127.0.0.1",
        port=port,
        log_level=os.getenv("HELIX_LOG_LEVEL", "info"),
    )


if __name__ == "__main__":
    main()
