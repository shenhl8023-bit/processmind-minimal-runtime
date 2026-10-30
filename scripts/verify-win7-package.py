#!/usr/bin/env python3
"""Verify an extracted ProcessMind Win7 package using only the stdlib."""

from __future__ import annotations

import argparse
from email.parser import BytesParser
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
    "docs/用户使用说明.md",
    "docs/系统简介.md",
    "docs/Win7功能测试方案-20261025.md",
    "docs/Win7缺陷清单-20261025.md",
    "scripts/win7_launcher.py",
    "prerequisites/README.md",
    "prerequisites/install-kb2533623.bat",
    "prerequisites/Windows6.1-KB2533623-x64.msu",
    "start-win7.bat",
    "stop-win7.cmd",
    "status-win7.cmd",
    ".env.example",
    "requirements-win7-py38.txt",
    "manifest.json",
)
CHECKSUM_LINE = re.compile(r"^(?P<digest>[0-9a-fA-F]{64})\s{2}(?P<path>.+?)\s*$")
# Trust the actual official x64 runtime, not the manifest's Python version.
# https://www.python.org/ftp/python/3.8.10/python-3.8.10-embed-amd64.zip
# Archive SHA-256: abbe314e9b41603dde0a823b76f5bbbe17b3de3e5ac4ef06b759da5466711271
CPYTHON38_CORE_SHA256 = {
    "python.exe": "5275c42f7359fa2c7ec473be3240e57d5ce5b9301a26bd2e98e89bb9db074581",
    "pythonw.exe": "a409db42d754c311d19921fbbf458c1abadc5142330cdb7f3c6016e97fa1116d",
    "python3.dll": "074b06ae1d0a0b5c26f0ce097c91e2f24a5d38b279849115495fc40c6c10117e",
    "python38.dll": "2f3e368f5bcc1dda5e951682008a509751e6395f7328fd0f02c4e1a11f67c128",
    "python38.zip": "613e0d63b54ed995273eda446eb09e51066e486f1e72b94f1c338a83dca3a021",
}
WIN7_COMPATIBILITY_DLLS = (
    "MSVCP140.dll", "VCRUNTIME140.dll", "VCRUNTIME140_1.dll", "ucrtbase.dll",
    "api-ms-win-crt-runtime-l1-1-0.dll", "api-ms-win-core-synch-l1-2-0.dll",
)


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
    if path == "start-win7.cmd":
        return True
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


def _canonical_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _check_runtime(root: Path, errors: List[str]) -> None:
    runtime = root / ".runtime/python"
    for name, digest in CPYTHON38_CORE_SHA256.items():
        path = runtime / name
        if not path.is_file() or _sha256(path) != digest:
            errors.append("CPython 3.8.10 x64 official runtime file missing or incorrect: %s" % name)

    top_level = {path.name.lower(): path for path in runtime.glob("*") if path.is_file()}
    for name in WIN7_COMPATIBILITY_DLLS:
        if name.lower() not in top_level:
            errors.append("missing Win7 compatibility DLL: %s" % name)
    allowed = set(CPYTHON38_CORE_SHA256) | {"python38._pth"}
    for name in top_level:
        if re.fullmatch(r"python\d+\.(?:dll|zip|_pth)", name) and name not in allowed:
            errors.append("unexpected Python runtime file: %s" % name)

    # Conservative checks for known regressions. This is not a complete Windows
    # API compatibility proof; Windows 7 execution remains a release check.
    for path in sorted(runtime.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in (".exe", ".dll", ".pyd"):
            continue
        data = path.read_bytes().lower()
        unsupported = [marker[:-1] for marker in (
            b"api-ms-win-core-path-l1-1-0.dll\0", b"bcryptprimitives.dll\0", b"processprng\0",
        ) if marker in data]
        unsupported.extend(match.group(0)[:-1] for match in re.finditer(rb"python(3\d*)\.dll\x00", data)
                           if match.group(1) not in (b"3", b"38"))
        for dependency in sorted(set(unsupported)):
            errors.append("known incompatible native dependency %s in %s" % (
                dependency.decode("ascii"), path.relative_to(root).as_posix()))

    lock_path = root / "requirements-win7-py38.txt"
    if not lock_path.is_file():
        return  # Reported by REQUIRED_PATHS.
    installed: Dict[str, List[str]] = {}
    for path in sorted(runtime.rglob("*.dist-info/METADATA")):
        with path.open("rb") as stream:
            metadata = BytesParser().parse(stream, headersonly=True)
        name, version = metadata.get("Name"), metadata.get("Version")
        if name and version:
            installed.setdefault(_canonical_name(name), []).append(version)
    for line in lock_path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([^\s;]+)", line)
        if match is None:
            errors.append("invalid Win7 dependency lock entry: %s" % line)
            continue
        name, version = _canonical_name(match.group(1)), match.group(2)
        actual = installed.get(name, [])
        if actual != [version]:
            errors.append("Win7 runtime dependency %s must be %s; installed: %s" % (
                name, version, ", ".join(actual) or "missing"))


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

    prerequisite = manifest.get("windows_prerequisite")
    if not isinstance(prerequisite, dict):
        errors.append("manifest windows_prerequisite must describe KB2533623")
    else:
        expected_prerequisite = {
            "id": "KB2533623",
            "installer": "prerequisites/install-kb2533623.bat",
            "payload": "prerequisites/Windows6.1-KB2533623-x64.msu",
            "reboot_required": True,
        }
        for key, value in expected_prerequisite.items():
            if prerequisite.get(key) != value:
                errors.append("manifest windows_prerequisite %s must be %r" % (key, value))

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

    _check_runtime(root, errors)
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
