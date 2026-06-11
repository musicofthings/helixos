#!/usr/bin/env python3
"""Build PyInstaller binaries for the HelixOS desktop shell."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def run_pyinstaller(args: list[str], cwd: Path) -> None:
    subprocess.run(args, cwd=cwd, check=True)


def build_api_binary(api_root: Path, dist_dir: Path) -> Path:
    name = "helixos-api"
    run_pyinstaller(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onefile",
            f"--name={name}",
            "--collect-submodules=helixos",
            "--hidden-import=uvicorn.logging",
            "--hidden-import=uvicorn.loops",
            "--hidden-import=uvicorn.loops.auto",
            "--hidden-import=uvicorn.protocols",
            "--hidden-import=uvicorn.protocols.http",
            "--hidden-import=uvicorn.protocols.http.auto",
            "--hidden-import=uvicorn.protocols.websockets",
            "--hidden-import=uvicorn.protocols.websockets.auto",
            "--hidden-import=uvicorn.lifespan",
            "--hidden-import=uvicorn.lifespan.on",
            "--hidden-import=sqlalchemy.dialects.postgresql",
            "--hidden-import=sqlalchemy.dialects.sqlite",
            "--hidden-import=psycopg",
            "scripts/run_sidecar.py",
        ],
        cwd=api_root,
    )
    built = api_root / "dist" / name
    if sys.platform == "win32":
        built = built.with_suffix(".exe")
    dist_dir.mkdir(parents=True, exist_ok=True)
    destination = dist_dir / built.name
    shutil.copy2(built, destination)
    return destination


def build_mcp_binary(repo_root: Path, dist_dir: Path) -> Path:
    name = "helixos-mcp-biopython"
    server_path = repo_root / "mcp/servers/biopython_local/server.py"
    run_pyinstaller(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onefile",
            f"--name={name}",
            str(server_path),
        ],
        cwd=repo_root,
    )
    built = repo_root / "dist" / name
    if sys.platform == "win32":
        built = built.with_suffix(".exe")
    dist_dir.mkdir(parents=True, exist_ok=True)
    destination = dist_dir / built.name
    shutil.copy2(built, destination)
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description="Build HelixOS desktop Python binaries")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("apps/desktop/resources/bin"),
        help="Directory where built binaries are copied",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[3]
    api_root = repo_root / "services/api"
    output_dir = (repo_root / args.output).resolve()

    try:
        import PyInstaller  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "PyInstaller is required. Install with: pip install -e 'services/api[desktop]'"
        ) from exc

    print(f"Building API sidecar binary into {output_dir}...")
    api_binary = build_api_binary(api_root, output_dir)
    print(f"Built {api_binary}")

    print(f"Building MCP binary into {output_dir}...")
    mcp_binary = build_mcp_binary(repo_root, output_dir)
    print(f"Built {mcp_binary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
