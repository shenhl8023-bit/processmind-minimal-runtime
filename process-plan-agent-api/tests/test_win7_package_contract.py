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


def test_win7_lock_uses_a_pydantic_core_build_that_supports_windows_7():
    contents = LOCK_FILE.read_text(encoding="utf-8")

    assert "pydantic==2.10.6" in contents
    assert "pydantic-core==2.27.2" in contents
    assert "pydantic-core==2.23.4" not in contents


def test_win7_lock_includes_anyio_python38_exception_group_dependency():
    contents = LOCK_FILE.read_text(encoding="utf-8")

    assert "anyio==4.4.0" in contents
    assert "exceptiongroup==1.2.2" in contents


def test_win7_lock_includes_pydantic_python38_annotation_backport():
    contents = LOCK_FILE.read_text(encoding="utf-8")

    assert "eval-type-backport==0.2.2" in contents


def test_win7_packaging_scripts_have_static_frontend_and_offline_contract():
    builder = PROJECT_ROOT / "scripts" / "build-win7-runtime.ps1"
    installer = PROJECT_ROOT / "scripts" / "install-win7-wheels.py"
    packer = PROJECT_ROOT / "scripts" / "pack-win7-windows.ps1"
    packer_cmd = PROJECT_ROOT / "scripts" / "pack-win7-windows.cmd"
    stage = PROJECT_ROOT / "scripts" / "stage-win7-package.ps1"

    for path in (builder, installer, packer, packer_cmd, stage):
        assert path.is_file(), path

    builder_text = builder.read_text(encoding="utf-8")
    packer_text = packer.read_text(encoding="utf-8")
    stage_text = stage.read_text(encoding="utf-8")
    assert "--no-index" in builder_text
    assert "--find-links" in builder_text
    assert "3.8.10" in builder_text
    assert "install-win7-wheels.py" in builder_text
    assert "import app.main" in builder_text
    assert "site-packages" in builder_text
    assert "import site" in builder_text
    assert "MSVCP140.dll" in builder_text
    assert "ucrtbase.dll" in builder_text
    assert "api-ms-win-crt-runtime-l1-1-0.dll" in builder_text
    assert "KB2533623" in packer_text
    assert "prerequisites" in packer_text
    assert "process-plan-agent-ui\\dist" in packer_text
    assert "manifest.json" in packer_text
    assert "SHA256SUMS.txt" in packer_text
    assert "ZipFile]::CreateFromDirectory" in packer_text
    assert "Compress-Archive -Path" not in packer_text
    assert "node_modules" in stage_text
    assert ".runtime/node" in stage_text or ".runtime\\node" in stage_text
    assert "node.exe" in stage_text
    assert ".env" in stage_text
    assert ".db" in stage_text
    assert "docs\\配置模板" in stage_text
    assert "docs\\用户使用说明.md" in stage_text
    assert "docs\\系统简介.md" in stage_text
    assert "docs\\Win7功能测试方案-20261025.md" in stage_text
    assert "docs\\Win7缺陷清单-20261025.md" in stage_text
    assert "prerequisites" in stage_text


def test_win7_entrypoints_are_present_and_do_not_require_node():
    assert not (PROJECT_ROOT / "start-win7.cmd").exists()
    for name in ("start-win7.bat", "stop-win7.cmd", "status-win7.cmd"):
        path = PROJECT_ROOT / name
        assert path.is_file()
        data = path.read_bytes()
        text = data.decode("utf-8")
        assert b"\r\n" in data
        assert b"\n" not in data.replace(b"\r\n", b"")
        if name == "start-win7.bat":
            assert "win7_launcher.py" in text
            assert "start-win7.cmd" not in text
            assert "pause" in text.lower()
        else:
            assert "win7_launcher.py" in text
        assert "node.exe" not in text.lower()
