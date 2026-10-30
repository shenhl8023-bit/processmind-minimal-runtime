import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
VERIFIER_PATH = PROJECT_ROOT / "scripts" / "verify-win7-package.py"


def _load_verifier():
    spec = importlib.util.spec_from_file_location("processmind_win7_verifier", VERIFIER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def verifier(monkeypatch):
    module = _load_verifier()
    # Keep vendor executables out of unit-test fixtures. Only replace the trust
    # anchors; exercise actual file reads, hashes and package validation below.
    monkeypatch.setattr(module, "CPYTHON38_CORE_SHA256", {
        name: hashlib.sha256(b"test CPython 3.8.10 x64 core\n").hexdigest()
        for name in ("python.exe", "pythonw.exe", "python3.dll", "python38.dll", "python38.zip")
    }, raising=False)
    return module


def _make_package(root: Path) -> None:
    required = (
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
    )
    for relative in required:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(relative.encode("utf-8"))

    runtime = root / ".runtime/python"
    for name in ("python.exe", "pythonw.exe", "python3.dll", "python38.dll", "python38.zip"):
        (runtime / name).write_bytes(b"test CPython 3.8.10 x64 core\n")
    for name in ("MSVCP140.dll", "VCRUNTIME140.dll", "VCRUNTIME140_1.dll", "ucrtbase.dll",
                 "api-ms-win-crt-runtime-l1-1-0.dll", "api-ms-win-core-synch-l1-2-0.dll"):
        (runtime / name).write_bytes(b"test Win7 compatibility library\n")
    (runtime / "python38._pth").write_text("python38.zip\n.\nsite-packages\nimport site\n", encoding="utf-8")
    lock = (PROJECT_ROOT / "requirements-win7-py38.txt").read_text(encoding="utf-8")
    (root / "requirements-win7-py38.txt").write_text(lock, encoding="utf-8")
    for line in lock.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        name, version = line.split("==")
        metadata = runtime / "site-packages" / ("%s-%s.dist-info" % (name, version)) / "METADATA"
        metadata.parent.mkdir(parents=True, exist_ok=True)
        metadata.write_text("Metadata-Version: 2.1\nName: %s\nVersion: %s\n\n" % (name, version), encoding="utf-8")

    manifest = {
        "package": "ProcessMind",
        "package_version": "1.0.0",
        "target_os": "Windows 7 SP1",
        "architecture": "x64",
        "python": "3.8.10",
        "frontend_target": "chrome109",
        "api": {"host": "127.0.0.1", "port": 8000},
        "browser_baseline": ["Chrome 109", "Edge 109"],
        "embedded_browser": False,
        "node_runtime_included": False,
        "windows_prerequisite": {
            "id": "KB2533623",
            "installer": "prerequisites/install-kb2533623.bat",
            "payload": "prerequisites/Windows6.1-KB2533623-x64.msu",
            "reboot_required": True,
        },
        "checksum_file": "SHA256SUMS.txt",
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    _write_checksums(root)


def _write_checksums(root: Path) -> None:
    lines = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == "SHA256SUMS.txt":
            continue
        relative = path.relative_to(root).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append("%s  %s" % (digest, relative))
    (root / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_readme_documents_win7_runtime_boundary():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    for needle in (
        "Python 3.8.10",
        "不需要 Node.js",
        "Chrome 109",
        "Edge 109",
        "start-win7.bat",
        "stop-win7.cmd",
        "%LOCALAPPDATA%\\ProcessMind",
        "IE11",
        "CEF/Qt",
        "KB2533623",
        "prerequisites\\install-kb2533623.bat",
    ):
        assert needle in readme


def test_verifier_accepts_valid_package(tmp_path: Path, verifier):
    _make_package(tmp_path)
    assert verifier.verify_package(tmp_path) == []


def test_verifier_rejects_missing_required_file(tmp_path: Path, verifier):
    _make_package(tmp_path)
    (tmp_path / "process-plan-agent-ui/dist/index.html").unlink()
    errors = verifier.verify_package(tmp_path)
    assert any("index.html" in error for error in errors)


def test_verifier_rejects_missing_win7_test_plan(tmp_path: Path, verifier):
    _make_package(tmp_path)
    relative = "docs/Win7功能测试方案-20261025.md"
    (tmp_path / relative).unlink()
    checksum_file = tmp_path / "SHA256SUMS.txt"
    retained = [
        line for line in checksum_file.read_text(encoding="utf-8").splitlines()
        if line.split("  ", 1)[1] != relative
    ]
    checksum_file.write_text("\n".join(retained) + "\n", encoding="utf-8")

    errors = verifier.verify_package(tmp_path)

    assert any("Win7功能测试方案-20261025.md" in error for error in errors)


def test_verifier_rejects_missing_env_example(tmp_path: Path, verifier):
    _make_package(tmp_path)
    (tmp_path / ".env.example").unlink()
    errors = verifier.verify_package(tmp_path)
    assert any(".env.example" in error for error in errors)


def test_verifier_rejects_modified_hash(tmp_path: Path, verifier):
    _make_package(tmp_path)
    (tmp_path / "start-win7.bat").write_text("changed", encoding="utf-8")
    errors = verifier.verify_package(tmp_path)
    assert any("SHA256" in error or "start-win7.bat" in error for error in errors)


def test_verifier_rejects_duplicate_start_command(tmp_path: Path, verifier):
    _make_package(tmp_path)
    duplicate = tmp_path / "start-win7.cmd"
    duplicate.write_text("obsolete", encoding="utf-8")
    errors = verifier.verify_package(tmp_path)
    assert any("start-win7.cmd" in error for error in errors)


@pytest.mark.parametrize("filename", ["python.exe", "python38.dll", "python38.zip"])
def test_verifier_rejects_wrong_core_even_with_valid_manifest_and_checksums(tmp_path, verifier, filename):
    _make_package(tmp_path)
    (tmp_path / ".runtime/python" / filename).write_bytes(b"Python 3.13 runtime, renamed if necessary")
    _write_checksums(tmp_path)

    errors = verifier.verify_package(tmp_path)

    assert any("CPython 3.8.10" in error and filename in error for error in errors)
    assert not any("SHA256 mismatch" in error for error in errors)


def test_verifier_rejects_mixed_python_versions(tmp_path, verifier):
    _make_package(tmp_path)
    (tmp_path / ".runtime/python/python313.dll").write_bytes(b"another Python runtime")
    _write_checksums(tmp_path)

    errors = verifier.verify_package(tmp_path)

    assert any("python313.dll" in error for error in errors)


@pytest.mark.parametrize("dependency", [
    b"api-ms-win-core-path-l1-1-0.dll\0", b"bcryptprimitives.dll\0", b"python313.dll\0",
])
def test_verifier_rejects_known_incompatible_native_dependencies(tmp_path, verifier, dependency):
    _make_package(tmp_path)
    extension = tmp_path / ".runtime/python/site-packages/example/_native.pyd"
    extension.parent.mkdir()
    extension.write_bytes(b"MZ\0" + dependency)
    _write_checksums(tmp_path)

    errors = verifier.verify_package(tmp_path)

    assert any("_native.pyd" in error and dependency[:-1].decode() in error for error in errors)


def test_verifier_rejects_runtime_dependencies_that_disagree_with_lock(tmp_path, verifier):
    _make_package(tmp_path)
    metadata = tmp_path / ".runtime/python/site-packages/pydantic-core-2.27.2.dist-info/METADATA"
    metadata.write_text("Metadata-Version: 2.1\nName: pydantic_core\nVersion: 2.46.4\n\n", encoding="utf-8")
    _write_checksums(tmp_path)

    errors = verifier.verify_package(tmp_path)

    assert any("pydantic-core" in error and "2.27.2" in error and "2.46.4" in error for error in errors)


def test_verifier_rejects_missing_runtime_compatibility_dll(tmp_path, verifier):
    _make_package(tmp_path)
    (tmp_path / ".runtime/python/ucrtbase.dll").unlink()
    _write_checksums(tmp_path)

    errors = verifier.verify_package(tmp_path)

    assert any("ucrtbase.dll" in error for error in errors)
