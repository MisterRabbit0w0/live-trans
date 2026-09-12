"""Reject private files and obvious secrets without printing matched values.

This project-specific check complements Gitleaks; it is not a complete secret
detector. Only files selected by Git are read. Ignored user settings stay local.
"""
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".py", ".qml", ".md", ".toml", ".yml", ".yaml", ".json", ".txt",
                 ".bat", ".ps1", ".iss", ".spec", ".svg", ".in"}
PRIVATE_PARTS = {".venv", ".venv-build", ".cache", "__pycache__", "dist", "build",
                 ".idea", ".vscode"}
SECRET_VALUE = re.compile(
    r'''(?i)["']?(?:\w*api[_-]?key|\w*token|\w*password|\w*secret)["']?'''
    r'''\s*(?::\s*str\s*)?[:=]\s*["']([^"'\r\n]{12,})["']'''
)
PATTERNS = {
    "private-key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "provider-token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[\w]{30,}|"
                                 r"sk-(?:proj-)?[A-Za-z0-9_-]{24,}|AKIA[A-Z0-9]{16})\b"),
    "user-home-path": re.compile(r"(?i)\b[A-Z]:[/\\]+Users[/\\]+[\w.-]+|/home/[\w.-]+"),
    "private-ip": re.compile(r"\b(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01]))"
                             r"\.\d{1,3}\.\d{1,3}\b"),
    "url-credentials": re.compile(r"https?://[^\s/@:]+:[^\s/@]+@"),
}


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def inspect_file(name: str, data: bytes):
    path = PurePosixPath(name)
    if (set(path.parts) & PRIVATE_PARTS or path.name in {"config.json", ".env"}
            or path.name.startswith(".env.") and path.name != ".env.example"
            or path.suffix.lower() in {".log", ".wav", ".pem", ".key", ".pfx", ".p12"}):
        yield "private-file", 0
    if path.suffix not in TEXT_SUFFIXES and path.name not in {
        "LICENSE", ".gitignore", ".gitattributes", "qmldir",
    }:
        return
    for number, line in enumerate(data.decode("utf-8", errors="replace").splitlines(), 1):
        for rule, pattern in PATTERNS.items():
            if pattern.search(line):
                if rule == "url-credentials" and (
                    "https://example-user:example-password@example.invalid/" in line
                ):
                    continue
                yield rule, number
        for match in SECRET_VALUE.finditer(line):
            value = match.group(1)
            # Explicit fixture/example placeholders only, never general file exemptions.
            if not (value.startswith(("example-", "test-", "your-", "${", "${{"))
                    or " " in value or value.startswith("http") or value == "translation-key"):
                yield "credential-assignment", number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", action="store_true", help="also scan all reachable commits")
    parser.add_argument("--staged", action="store_true", help="scan index blobs, not working files")
    args = parser.parse_args()
    failed, count = False, 0

    def check(name, data, revision="working-tree"):
        nonlocal failed, count
        count += 1
        for rule, number in inspect_file(name, data):
            failed = True
            print(f"{revision}: {name}:{number}: {rule} (value redacted)")

    if args.staged:
        names = git("ls-files", "-z").decode().split("\0")
        for name in filter(None, names):
            check(name, git("show", f":{name}"), "index")
    else:
        names = git("ls-files", "--cached", "--others", "--exclude-standard", "-z")
        for name in filter(None, names.decode().split("\0")):
            path = ROOT / name
            if path.is_file():
                check(name, path.read_bytes())
    if args.history:
        seen = set()
        for rev in git("rev-list", "--all").decode().splitlines():
            for entry in git("ls-tree", "-r", "-z", rev).split(b"\0"):
                if not entry:
                    continue
                metadata, name = entry.split(b"\t", 1)
                mode, kind, blob = metadata.split()
                if kind != b"blob" or (name, blob) in seen:
                    continue
                seen.add((name, blob))
                check(name.decode(), git("cat-file", "blob", blob.decode()), rev[:12])
    print(f"Public-tree audit: {count} files/blobs, {'FAILED' if failed else 'passed'}")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
