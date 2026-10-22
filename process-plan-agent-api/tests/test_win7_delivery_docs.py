import hashlib
import importlib.util
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
VERIFIER_PATH = PROJECT_ROOT / "scripts" / "verify-win7-package.py"


def _load_verifier():
    spec = importlib.util.spec_from_file_location("processmind_win7_verifier", VERIFIER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _make_package(root: Path) -> None:
    required = (
        ".runtime/python/python.exe",
        "process-plan-agent-api/app/main.py",
        "process-plan-agent-ui/dist/index.html",
        "scripts/win7_launcher.py",
        "start-win7.cmd",
        "stop-win7.cmd",
        "status-win7.cmd",
    )
    for relative in required:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(relative.encode("utf-8"))

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
        "checksum_file": "SHA256SUMS.txt",
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    lines = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == "SHA256SUMS.txt":
            continue
        relative = path.relative_to(root).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append("%s  %s" % (digest, relative))
    (root / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="ascii")


def test_readme_documents_win7_runtime_boundary():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    for needle in (
        "Python 3.8.10",
        "不需要 Node.js",
        "Chrome 109",
        "Edge 109",
        "start-win7.cmd",
        "stop-win7.cmd",
        "%LOCALAPPDATA%\\ProcessMind",
        "IE11",
        "CEF/Qt",
    ):
        assert needle in readme


def test_verifier_accepts_valid_package(tmp_path: Path):
    verifier = _load_verifier()
    _make_package(tmp_path)
    assert verifier.verify_package(tmp_path) == []


def test_verifier_rejects_missing_required_file(tmp_path: Path):
    verifier = _load_verifier()
    _make_package(tmp_path)
    (tmp_path / "process-plan-agent-ui/dist/index.html").unlink()
    errors = verifier.verify_package(tmp_path)
    assert any("index.html" in error for error in errors)


def test_verifier_rejects_modified_hash(tmp_path: Path):
    verifier = _load_verifier()
    _make_package(tmp_path)
    (tmp_path / "start-win7.cmd").write_text("changed", encoding="utf-8")
    errors = verifier.verify_package(tmp_path)
    assert any("SHA256" in error or "start-win7.cmd" in error for error in errors)
