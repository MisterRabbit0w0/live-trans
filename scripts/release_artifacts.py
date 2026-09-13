"""Validate a tag and release payload before granting it a GitHub Release."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

from build_windows import app_version


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-tag", action="store_true")
    parser.add_argument("--directory", type=Path)
    args = parser.parse_args()
    version = app_version()
    if os.environ.get("GITHUB_REF") != f"refs/tags/v{version}":
        raise SystemExit(f"Release tag must match pyproject.toml: v{version}")
    if args.validate_tag:
        print(f"Release version validated: {version}")
        return
    if not args.directory:
        parser.error("--directory is required when checking release payloads")
    directory = args.directory
    stem = f"LiveTrans-{version}-windows-x64"
    windows = {f"{stem}-portable.zip", f"{stem}-standalone.exe", f"{stem}-setup.exe",
               "build-info.json", "third-party-licenses.zip"}
    expected = windows | {"SHA256SUMS.txt", f"livetrans-{version}-py3-none-any.whl",
                          f"livetrans-{version}.tar.gz"}
    present = {path.name for path in directory.iterdir() if path.is_file()}
    if present != expected:
        raise SystemExit(
            f"Unexpected release set: missing={expected-present}, extra={present-expected}",
        )
    checksums = {}
    full_checksum_set = expected - {"SHA256SUMS.txt"}
    for line in (directory / "SHA256SUMS.txt").read_text("utf-8").splitlines():
        checksum, name = line.split("  ", 1)
        if name not in full_checksum_set or name in checksums:
            raise SystemExit("Invalid or duplicate name in Windows checksum manifest")
        checksums[name] = checksum
    if set(checksums) not in (windows, full_checksum_set):
        raise SystemExit("Checksum manifest is incomplete or has an unexpected format")
    for name, expected_hash in checksums.items():
        if digest(directory / name) != expected_hash:
            raise SystemExit(f"Checksum mismatch: {name}")
    info = json.loads((directory / "build-info.json").read_text("utf-8"))
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
    if info["version"] != version or info["commit"] != revision or info["dirty"]:
        raise SystemExit("Windows binaries do not match the clean tagged source")
    all_checksums = [f"{digest(directory / name)}  {name}"
                     for name in sorted(present - {"SHA256SUMS.txt"})]
    (directory / "SHA256SUMS.txt").write_text("\n".join(all_checksums) + "\n", encoding="utf-8")
    print("Complete release payload verified")


if __name__ == "__main__":
    main()
