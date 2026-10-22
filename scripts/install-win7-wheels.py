#!/usr/bin/env python3
"""Install a pinned CPython 3.8 Windows wheelhouse without requiring pip.

The Win7 embeddable Python distribution intentionally does not include pip.
This installer handles the wheel subset used by ProcessMind and only accepts
tags compatible with CPython 3.8 on Windows x64.
"""

from __future__ import print_function

import argparse
import io
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
import zipfile


TARGET_PYTHON = (3, 8)
TARGET_PLATFORM = "win_amd64"
WHEEL_SUFFIX = ".whl"
_REQUIREMENT_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;#]+)$")
_METADATA_FIELD_RE = re.compile(r"^(Name|Version):\s*(.+?)\s*$", re.MULTILINE)
_TAG_RE = re.compile(r"^([A-Za-z0-9.]+)-([A-Za-z0-9.]+)-([A-Za-z0-9_]+)$")


class WheelInstallError(Exception):
    """Raised when the wheelhouse cannot satisfy the locked runtime."""


def normalize_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", str(value).strip()).lower()


def read_requirements(path: Path) -> List[Tuple[str, str]]:
    requirements: List[Tuple[str, str]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # Keep the lock intentionally strict.  A marker or an unpinned
        # requirement would make an offline package non-reproducible.
        line = line.split(" #", 1)[0].strip()
        match = _REQUIREMENT_RE.match(line)
        if not match:
            raise WheelInstallError(
                "requirements line %d is not an exact name==version pin: %s"
                % (line_number, raw)
            )
        requirements.append((normalize_name(match.group(1)), match.group(2)))
    if not requirements:
        raise WheelInstallError("requirements lock is empty: %s" % path)
    return requirements


def _metadata_value(text: str, field: str) -> str:
    match = re.search(r"^%s:\s*(.+?)\s*$" % re.escape(field), text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _wheel_tags(archive: zipfile.ZipFile) -> List[str]:
    wheel_files = [name for name in archive.namelist() if name.endswith(".dist-info/WHEEL")]
    if len(wheel_files) != 1:
        raise WheelInstallError("wheel has an invalid WHEEL metadata file")
    text = archive.read(wheel_files[0]).decode("utf-8")
    tags = []
    for line in text.splitlines():
        if line.startswith("Tag:"):
            tags.append(line.split(":", 1)[1].strip())
    if not tags:
        raise WheelInstallError("wheel has no Tag metadata")
    return tags


def _version_from_python_tag(tag: str) -> Optional[Tuple[int, int]]:
    match = re.match(r"^cp(\d)(\d+)$", tag)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def is_compatible_tag(tag: str) -> bool:
    match = _TAG_RE.match(tag)
    if not match:
        return False
    python_tag, abi_tag, platform_tag = match.groups()

    # Pure Python wheels may publish multiple tags (for example py2 and py3).
    if platform_tag == "any":
        return python_tag == "py3" or python_tag in ("py2.py3", "py2.py3.py4")

    if platform_tag != TARGET_PLATFORM:
        return False
    if python_tag != "cp38" and abi_tag != "abi3":
        return False
    if python_tag == "cp38":
        return abi_tag in ("cp38", "abi3", "none")

    # An abi3 extension compiled for an older CPython is loadable by 3.8.
    abi3_version = _version_from_python_tag(python_tag)
    return abi_tag == "abi3" and abi3_version is not None and abi3_version <= TARGET_PYTHON


def _wheel_identity(archive: zipfile.ZipFile) -> Tuple[str, str]:
    metadata_files = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
    if len(metadata_files) != 1:
        raise WheelInstallError("wheel has an invalid METADATA file")
    text = archive.read(metadata_files[0]).decode("utf-8")
    name = _metadata_value(text, "Name")
    version = _metadata_value(text, "Version")
    if not name or not version:
        raise WheelInstallError("wheel metadata is missing Name or Version")
    return normalize_name(name), version


def _safe_member_name(name: str) -> Path:
    normal = name.replace("\\", "/")
    parts = normal.split("/")
    if (
        not normal
        or normal.startswith("/")
        or re.match(r"^[A-Za-z]:", normal)
        or any(part in ("", ".", "..") for part in parts)
    ):
        raise WheelInstallError("wheel contains an unsafe path: %s" % name)
    return Path(*parts)


def _destination_for_member(member: Path, target: Path) -> Optional[Path]:
    parts = member.parts
    if len(parts) >= 2 and parts[0].endswith(".data"):
        category = parts[1]
        remainder = parts[2:]
        if category in ("purelib", "platlib"):
            return target.joinpath(*remainder)
        if category == "scripts":
            return target.parent / "Scripts" / Path(*remainder)
        if category == "headers":
            return target.parent / "include" / Path(*remainder)
        if category == "data":
            return target.parent.joinpath(*remainder)
        raise WheelInstallError("wheel contains unsupported .data category: %s" % category)
    return target / member


def _members_to_install(archive: zipfile.ZipFile, target: Path) -> Iterable[Tuple[zipfile.ZipInfo, Path]]:
    for info in archive.infolist():
        if info.is_dir():
            continue
        member = _safe_member_name(info.filename)
        # Wheel records and metadata are useful at runtime, while RECORD is
        # generated by pip but is not required for imports.
        if member.name == "RECORD" and member.parent.name.endswith(".dist-info"):
            continue
        destination = _destination_for_member(member, target)
        if destination is None:
            continue
        yield info, destination


def _copy_archive(archive: zipfile.ZipFile, target: Path) -> None:
    for info, destination in _members_to_install(archive, target):
        destination.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(info, "r") as source, destination.open("wb") as output:
            shutil.copyfileobj(source, output)


def _find_wheels(wheelhouse: Path) -> List[Path]:
    return sorted(path for path in wheelhouse.glob("*.whl") if path.is_file())


def _select_wheels(requirements: Sequence[Tuple[str, str]], wheelhouse: Path) -> List[Path]:
    available: Dict[Tuple[str, str], List[Path]] = {}
    incompatibilities: Dict[Tuple[str, str], List[str]] = {}
    for wheel in _find_wheels(wheelhouse):
        try:
            with zipfile.ZipFile(str(wheel), "r") as archive:
                identity = _wheel_identity(archive)
                tags = _wheel_tags(archive)
        except (OSError, zipfile.BadZipFile, UnicodeError, WheelInstallError) as exc:
            raise WheelInstallError("cannot inspect wheel %s: %s" % (wheel.name, exc))
        if any(is_compatible_tag(tag) for tag in tags):
            available.setdefault(identity, []).append(wheel)
        else:
            incompatibilities.setdefault(identity, []).append("%s (%s)" % (wheel.name, ", ".join(tags)))

    selected = []
    for requirement in requirements:
        candidates = available.get(requirement, [])
        if len(candidates) > 1:
            raise WheelInstallError("multiple compatible wheels found for %s==%s: %s" % (
                requirement[0], requirement[1], ", ".join(path.name for path in candidates)
            ))
        if not candidates:
            incompatible = incompatibilities.get(requirement, [])
            detail = "; incompatible candidates: %s" % ", ".join(incompatible) if incompatible else ""
            raise WheelInstallError("no compatible wheel for %s==%s%s" % (requirement[0], requirement[1], detail))
        selected.append(candidates[0])
    return selected


def install_requirements(requirements_path: Path, wheelhouse: Path, target: Path) -> List[str]:
    requirements_path = Path(requirements_path).resolve()
    wheelhouse = Path(wheelhouse).resolve()
    target = Path(target).resolve()
    if not requirements_path.is_file():
        raise WheelInstallError("requirements lock does not exist: %s" % requirements_path)
    if not wheelhouse.is_dir():
        raise WheelInstallError("wheelhouse does not exist: %s" % wheelhouse)
    requirements = read_requirements(requirements_path)
    selected = _select_wheels(requirements, wheelhouse)

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix="processmind-wheel-install-", dir=str(target.parent)))
    try:
        for wheel in selected:
            with zipfile.ZipFile(str(wheel), "r") as archive:
                _copy_archive(archive, temporary)
        if target.exists():
            shutil.rmtree(str(target))
        temporary.rename(str(target))
        temporary = None  # type: ignore
    finally:
        if temporary is not None and temporary.exists():
            shutil.rmtree(str(temporary), ignore_errors=True)
    return ["%s==%s" % requirement for requirement in requirements]


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requirements", type=Path, required=True)
    parser.add_argument("--wheelhouse", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        installed = install_requirements(args.requirements, args.wheelhouse, args.target)
    except (OSError, WheelInstallError) as exc:
        print("Win7 wheel installation failed: %s" % exc, file=sys.stderr)
        return 1
    print("Installed %d Win7 wheels into %s" % (len(installed), args.target.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
