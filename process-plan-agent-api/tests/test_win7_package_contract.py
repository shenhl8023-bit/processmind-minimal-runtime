from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOCK_FILE = PROJECT_ROOT / "requirements-win7-py38.txt"


def _requirement_names():
    lines = []
    for raw in LOCK_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            lines.append(line.split("==", 1)[0].lower())
    return lines


def test_win7_lock_is_fully_pinned_and_contains_runtime_dependencies():
    assert LOCK_FILE.is_file()
    contents = LOCK_FILE.read_text(encoding="utf-8")
    assert "Python 3.8.10" in contents
    assert "fastapi==" in contents
    assert "uvicorn==" in contents
    assert "sqlalchemy==" in contents.lower()
    assert "pymupdf==" in contents.lower()
    assert "py7zr==" in contents.lower()

    requirements = [
        line.strip()
        for line in contents.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert requirements
    assert all("==" in line for line in requirements)
    assert not any("node" in name for name in _requirement_names())


def test_win7_packaging_scripts_have_static_frontend_and_offline_contract():
    builder = PROJECT_ROOT / "scripts" / "build-win7-runtime.ps1"
    packer = PROJECT_ROOT / "scripts" / "pack-win7-windows.ps1"
    packer_cmd = PROJECT_ROOT / "scripts" / "pack-win7-windows.cmd"
    stage = PROJECT_ROOT / "scripts" / "stage-win7-package.ps1"

    for path in (builder, packer, packer_cmd, stage):
        assert path.is_file(), path

    builder_text = builder.read_text(encoding="utf-8")
    packer_text = packer.read_text(encoding="utf-8")
    stage_text = stage.read_text(encoding="utf-8")
    assert "--no-index" in builder_text
    assert "--find-links" in builder_text
    assert "3.8.10" in builder_text
    assert "process-plan-agent-ui\\dist" in packer_text
    assert "manifest.json" in packer_text
    assert "SHA256SUMS.txt" in packer_text
    assert "node_modules" in stage_text
    assert ".runtime/node" in stage_text or ".runtime\\node" in stage_text
    assert ".env" in stage_text
    assert ".db" in stage_text


def test_win7_entrypoints_are_present_and_do_not_require_node():
    for name in ("start-win7.cmd", "stop-win7.cmd", "status-win7.cmd"):
        path = PROJECT_ROOT / name
        assert path.is_file()
        text = path.read_text(encoding="utf-8")
        assert "win7_launcher.py" in text
        assert "node.exe" not in text.lower()
