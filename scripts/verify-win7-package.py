#!/usr/bin/env python3
"""Verify an extracted ProcessMind Win7 package using only the stdlib."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Dict, Iterable, List, Optional, Tuple


REQUIRED_PATHS = (
    ".runtime/python/python.exe",
    "process-plan-agent-api/app/main.py",
    "process-plan-agent-ui/dist/index.html",
    "docs/配置模板/第三步规则分析-问题树节点配置.template.json",
    "scripts/win7_launcher.py",
    "start-win7.cmd",
    "stop-win7.cmd",
    "status-win7.cmd",
    "manifest.json",
)
CHECKSUM_LINE = re.compile(r"^(?P<digest>[0-9a-fA-F]{64})\s{2}(?P<path>.+?)\s*$")


def _normalise_relative(value: str) -> Optional[str]:
    candidate = value.replace("\\", "/").strip()
    if not candidate:
        return None
    path = PurePosixPath(candidate)
    if path.is_absolute() or ".." in path.parts:
        return None
    return "/".join(part for part in path.parts if part not in ("", "."))


def _is_forbidden(relative: str) -> bool:
    path = relative.lower()
    parts = path.split("/")
    name = parts[-1]
    if "node_modules" in parts:
        return True
    if len(parts) >= 2 and parts[0:2] == [".runtime", "node"]:
        return True
    if any(part == ".runtime" and index + 1 < len(parts) and parts[index + 1] == "node" for index, part in enumerate(parts)):
        return True
    if name not in (".env.example", ".env.compose.example") and any(part.startswith(".env") for part in parts):
        return True
    if any(part in ("__pycache__", ".pytest_cache") for part in parts) or name.endswith((".pyc", ".pyo")):
        return True
    if any(part in ("upload", "uploads", "log", "logs") for part in parts):
        return True
    if name.endswith((".db", ".sqlite", ".sqlite3", ".db-wal", ".db-shm", ".sqlite-wal", ".sqlite-shm")):
        return True
    if name in ("node.exe", "node-license.txt", "npm.cmd", "npx.cmd"):
        return True
    if name in ("process_settings.json", "credentials.json", ".npmrc", ".pypirc"):
        return True
    return False


def _iter_files(root: Path) -> Iterable[Tuple[str, Path]]:
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        yield relative, path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _load_manifest(root: Path, errors: List[str]) -> Optional[Dict[str, object]]:
    path = root / "manifest.json"
    if not path.is_file():
        errors.append("missing manifest.json")
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        errors.append("manifest.json is not valid JSON: %s" % exc)
        return None
    if not isinstance(value, dict):
        errors.append("manifest.json must contain an object")
        return None
    return value


def _check_manifest(manifest: Dict[str, object], errors: List[str]) -> str:
    expected = {
        "package": "ProcessMind",
        "target_os": "Windows 7 SP1",
        "architecture": "x64",
        "python": "3.8.10",
        "frontend_target": "chrome109",
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            errors.append("manifest %s must be %r" % (key, value))

    api = manifest.get("api")
    if not isinstance(api, dict) or api.get("host") != "127.0.0.1" or api.get("port") != 8000:
        errors.append("manifest api must bind 127.0.0.1:8000")

    browsers = manifest.get("browser_baseline")
    if not isinstance(browsers, list) or "Chrome 109" not in browsers or "Edge 109" not in browsers:
        errors.append("manifest browser_baseline must include Chrome 109 and Edge 109")
    if manifest.get("embedded_browser") is not False:
        errors.append("manifest embedded_browser must be false")
    if manifest.get("node_runtime_included") is not False:
        errors.append("manifest node_runtime_included must be false")

    checksum_file = manifest.get("checksum_file", "SHA256SUMS.txt")
    if not isinstance(checksum_file, str):
        errors.append("manifest checksum_file must be a relative path")
        return "SHA256SUMS.txt"
    normalised = _normalise_relative(checksum_file)
    if normalised is None:
        errors.append("manifest checksum_file must be a relative path")
        return "SHA256SUMS.txt"
    return normalised


def _load_checksums(root: Path, relative: str, errors: List[str]) -> Dict[str, str]:
    path = root / Path(*relative.split("/"))
    if not path.is_file():
        errors.append("missing checksum file: %s" % relative)
        return {}
    checksums: Dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError) as exc:
        errors.append("cannot read %s: %s" % (relative, exc))
        return {}
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        match = CHECKSUM_LINE.match(line)
        if not match:
            errors.append("invalid SHA256 line %d in %s" % (line_number, relative))
            continue
        target = _normalise_relative(match.group("path"))
        if target is None:
            errors.append("invalid checksum path on line %d in %s" % (line_number, relative))
            continue
        if target in checksums:
            errors.append("duplicate checksum entry: %s" % target)
            continue
        checksums[target] = match.group("digest").lower()
    return checksums


def verify_package(package_root: Path) -> List[str]:
    """Return actionable verification errors; an empty list means valid."""

    root = Path(package_root).expanduser().resolve()
    errors: List[str] = []
    if not root.is_dir():
        return ["package directory does not exist: %s" % root]

    manifest = _load_manifest(root, errors)
    checksum_relative = _check_manifest(manifest, errors) if manifest is not None else "SHA256SUMS.txt"

    for relative in REQUIRED_PATHS:
        path = root / Path(*relative.split("/"))
        if not path.is_file():
            errors.append("missing required package path: %s" % relative)

    checksums = _load_checksums(root, checksum_relative, errors)
    checksum_path = root / Path(*checksum_relative.split("/"))
    actual_files = {}
    for relative, path in _iter_files(root):
        if path.is_symlink():
            errors.append("symbolic link is not allowed: %s" % relative)
        if _is_forbidden(relative):
            errors.append("forbidden package artifact: %s" % relative)
        if relative != checksum_relative:
            actual_files[relative] = path

    for relative, path in actual_files.items():
        expected = checksums.get(relative)
        if expected is None:
            errors.append("missing SHA256 entry: %s" % relative)
            continue
        actual = _sha256(path)
        if actual != expected:
            errors.append("SHA256 mismatch: %s" % relative)

    for relative in checksums:
        if relative == checksum_relative:
            errors.append("checksum file must not hash itself: %s" % relative)
            continue
        path = root / Path(*relative.split("/"))
        if not path.is_file():
            errors.append("checksum references missing file: %s" % relative)

    return errors


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path, help="extracted Win7 package directory")
    args = parser.parse_args(argv)
    errors = verify_package(args.package)
    if errors:
        for error in errors:
            print("ERROR: %s" % error, file=sys.stderr)
        return 1
    print("Win7 package verification passed: %s" % Path(args.package).resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
