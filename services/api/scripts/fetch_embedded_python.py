#!/usr/bin/env python3
"""Download an embedded CPython runtime for HelixOS desktop builds."""

from __future__ import annotations

import argparse
import platform
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

RELEASE_TAG = "20241016"
PYTHON_VERSION = "3.12.7"


def resolve_triplet() -> str:
    system = platform.system()
    machine = platform.machine().lower()

    if system == "Darwin":
        return "aarch64-apple-darwin" if machine in {"arm64", "aarch64"} else "x86_64-apple-darwin"
    if system == "Linux":
        return "aarch64-unknown-linux-gnu" if machine in {"arm64", "aarch64"} else "x86_64-unknown-linux-gnu"
    if system == "Windows":
        return "x86_64-pc-windows-msvc"
    raise SystemExit(f"Unsupported platform for embedded Python: {system} {machine}")


def download_runtime(output_dir: Path) -> Path:
    triplet = resolve_triplet()
    filename = f"cpython-{PYTHON_VERSION}+{RELEASE_TAG}-{triplet}-install_only.tar.gz"
    url = f"https://github.com/indygreg/python-build-standalone/releases/download/{RELEASE_TAG}/{filename}"

    output_dir.mkdir(parents=True, exist_ok=True)
    if (output_dir / "bin").exists():
        print(f"Embedded Python already present at {output_dir}")
        return output_dir / "bin" / ("python.exe" if platform.system() == "Windows" else "python3")

    print(f"Downloading embedded Python from {url}")
    with tempfile.TemporaryDirectory() as tmp:
        archive_path = Path(tmp) / filename
        urllib.request.urlretrieve(url, archive_path)
        with tarfile.open(archive_path) as archive:
            archive.extractall(tmp)
        extracted_root = next(path for path in Path(tmp).iterdir() if path.is_dir())
        if output_dir.exists():
            shutil.rmtree(output_dir)
        shutil.copytree(extracted_root, output_dir)

    python_name = "python.exe" if platform.system() == "Windows" else "python3"
    return output_dir / "bin" / python_name


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch embedded Python runtime")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("apps/desktop/resources/python"),
        help="Directory where the runtime should be extracted",
    )
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parents[3]
    output_dir = (repo_root / args.output).resolve()
    python_path = download_runtime(output_dir)
    print(f"Embedded Python ready at {python_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
