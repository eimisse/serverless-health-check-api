#!/usr/bin/env python3
"""Build a minimal, byte-reproducible Lambda ZIP and report its SHA-256."""

from __future__ import annotations

import hashlib
import stat
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAMBDA_DIR = ROOT / "lambda"
DEFAULT_OUTPUT = ROOT / "build" / "lambda.zip"
FIXED_ZIP_TIME = (2020, 1, 1, 0, 0, 0)
PACKAGE_FILES = ((LAMBDA_DIR / "handler.py", "handler.py"),)


def _zip_info(archive_name: str) -> zipfile.ZipInfo:
    """Return platform-independent metadata for one regular ZIP member."""
    info = zipfile.ZipInfo(archive_name, FIXED_ZIP_TIME)
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3  # Unix; avoids host-dependent Windows metadata.
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    return info


def build(output: Path = DEFAULT_OUTPUT) -> str:
    """Build the archive atomically and return its lowercase SHA-256 digest."""
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = output.with_suffix(f"{output.suffix}.tmp")

    try:
        with zipfile.ZipFile(temporary_output, mode="w") as archive:
            for source, archive_name in sorted(PACKAGE_FILES, key=lambda entry: entry[1]):
                archive.writestr(_zip_info(archive_name), source.read_bytes())
        temporary_output.replace(output)
    finally:
        temporary_output.unlink(missing_ok=True)

    return hashlib.sha256(output.read_bytes()).hexdigest()


def main() -> int:
    digest = build()
    print(f"lambda_package_path={DEFAULT_OUTPUT.relative_to(ROOT).as_posix()}")
    print(f"lambda_package_bytes={DEFAULT_OUTPUT.stat().st_size}")
    print(f"lambda_package_sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
