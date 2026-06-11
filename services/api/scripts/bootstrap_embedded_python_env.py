#!/usr/bin/env python3
"""Create a self-contained Python environment for packaged HelixOS desktop builds."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap embedded Python venv for desktop")
    parser.add_argument(
        "--python-root",
        type=Path,
        default=Path("apps/desktop/resources/python"),
        help="Embedded Python runtime directory",
    )
    parser.add_argument(
        "--venv-root",
        type=Path,
        default=Path("apps/desktop/resources/pyvenv"),
        help="Target venv directory",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[3]
    python_root = (repo_root / args.python_root).resolve()
    venv_root = (repo_root / args.venv_root).resolve()
    api_root = repo_root / "services/api"

    python_name = "python.exe" if sys.platform == "win32" else "python3"
    embedded_python = python_root / "bin" / python_name
    if not embedded_python.exists():
        raise SystemExit(
            f"Embedded Python not found at {embedded_python}. Run scripts/fetch_embedded_python.py first."
        )

    if venv_root.exists():
        import shutil

        shutil.rmtree(venv_root)

    print(f"Creating desktop venv at {venv_root}")
    subprocess.run([str(embedded_python), "-m", "venv", str(venv_root)], check=True)

    pip_name = "pip.exe" if sys.platform == "win32" else "pip"
    pip_executable = venv_root / "bin" / pip_name
    subprocess.run([str(pip_executable), "install", "--upgrade", "pip"], check=True)
    subprocess.run([str(pip_executable), "install", "-e", f"{api_root}[desktop]"], check=True)
    print("Desktop Python environment ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
