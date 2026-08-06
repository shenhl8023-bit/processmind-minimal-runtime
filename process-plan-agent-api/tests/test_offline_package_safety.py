from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
STAGE_SCRIPT = PROJECT_ROOT / "scripts" / "stage-offline-package.ps1"


def _write(root: Path, relative_path: str, content: str = "fixture") -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _stage(source: Path, destination: Path) -> subprocess.CompletedProcess[str]:
    assert POWERSHELL is not None
    return subprocess.run(
        [
            POWERSHELL,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(STAGE_SCRIPT),
            "-SourceRoot",
            str(source),
            "-Destination",
            str(destination),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is required for the Windows packager")
def test_stage_excludes_runtime_data_settings_and_env_files(tmp_path: Path):
    source = tmp_path / "source"
    destination = tmp_path / "stage"
    _write(source, ".runtime/python/python.exe")
    _write(source, ".runtime/python/Lib/site-packages/sample/data/schema.json", "{}")
    _write(
        source,
        ".runtime/python/Lib/site-packages/certifi/cacert.pem",
        "-----BEGIN CERTIFICATE-----\npublic-ca-certificate\n-----END CERTIFICATE-----\n",
    )
    _write(source, "process-plan-agent-api/app/main.py")
    _write(source, "process-plan-agent-ui/src/main.ts")
    _write(source, "process-plan-agent-ui/node_modules/vite/bin/vite.js")
    _write(source, "docs/配置模板/第五步参数问答策略.json", '{"version":"1.0.0"}')
    _write(source, "scripts/example.ps1")
    _write(source, "README.md")
    _write(source, ".env.example", "LLM_API_KEY=\n")
    _write(source, ".env.compose.example", "LLM_API_KEY=\n")
    _write(source, "docker-compose.yml", "LLM_API_KEY: ${LLM_API_KEY:-}\n")

    live_value = "local-secret-that-must-not-ship"
    _write(source, ".env", f"LLM_API_KEY={live_value}\n")
    _write(source, "data/config/process_settings.json", f'{{"LLM_API_KEY":"{live_value}"}}')
    _write(source, "data/db/process_mind.db", live_value)
    _write(source, "process-plan-agent-api/process_settings.json", live_value)
    _write(source, "process-plan-agent-api/process_mind.db", live_value)
    _write(source, "process-plan-agent-api/uploads/customer.pdf", live_value)

    result = _stage(source, destination)

    assert result.returncode == 0, result.stdout + result.stderr
    assert (destination / "process-plan-agent-api/app/main.py").is_file()
    assert (destination / "process-plan-agent-ui/node_modules/vite/bin/vite.js").is_file()
    assert (destination / ".runtime/python/Lib/site-packages/sample/data/schema.json").is_file()
    assert (destination / ".runtime/python/Lib/site-packages/certifi/cacert.pem").is_file()
    assert (destination / ".env.example").read_text(encoding="utf-8") == "LLM_API_KEY=\n"
    assert (destination / "docker-compose.yml").is_file()
    assert (destination / "docs/配置模板/第五步参数问答策略.json").is_file()
    assert not (destination / ".env").exists()
    assert not (destination / "data").exists()
    assert not (destination / "process-plan-agent-api/process_settings.json").exists()
    assert not (destination / "process-plan-agent-api/process_mind.db").exists()
    assert not (destination / "process-plan-agent-api/uploads").exists()


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is required for the Windows packager")
def test_stage_fails_when_allowed_config_contains_a_real_secret(tmp_path: Path):
    source = tmp_path / "source"
    destination = tmp_path / "stage"
    live_value = "live-secret-value-1234567890"
    _write(source, "process-plan-agent-api/app/main.py")
    _write(source, "process-plan-agent-api/deployment.json", f'{{"LLM_API_KEY":"{live_value}"}}')

    result = _stage(source, destination)

    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "non-placeholder secret" in output
    assert "deployment.json" in output
    assert live_value not in output


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is required for the Windows packager")
def test_stage_fails_when_source_code_contains_a_static_secret(tmp_path: Path):
    source = tmp_path / "source"
    destination = tmp_path / "stage"
    key_name = "LLM_" + "API_KEY"
    live_value = "source-live-value-1234567890"
    _write(source, "process-plan-agent-api/app/main.py", f'{key_name} = "{live_value}"\n')

    result = _stage(source, destination)

    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "non-placeholder secret" in output
    assert "main.py" in output
    assert live_value not in output


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is required for the Windows packager")
@pytest.mark.parametrize(
    ("relative_path", "content"),
    [
        (".runtime/python/runtime.properties", "LLM_API_KEY=runtime-live-value-1234567890\n"),
        (
            "process-plan-agent-ui/node_modules/example/config.xml",
            "<settings><LLM_API_KEY>node-live-value-1234567890</LLM_API_KEY></settings>\n",
        ),
        (
            "process-plan-agent-api/deployment.csv",
            "LLM_API_KEY,csv-live-value-1234567890\n",
        ),
    ],
)
def test_stage_scans_runtime_dependency_and_common_config_formats(
    tmp_path: Path,
    relative_path: str,
    content: str,
):
    source = tmp_path / "source"
    destination = tmp_path / "stage"
    _write(source, relative_path, content)

    result = _stage(source, destination)

    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "non-placeholder secret" in output
    assert Path(relative_path).name in output
    assert "live-value" not in output


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is required for the Windows packager")
def test_stage_scans_high_confidence_assignments_in_bundled_dependency_source(tmp_path: Path):
    source = tmp_path / "source"
    destination = tmp_path / "stage"
    key_name = "LLM_" + "API_KEY"
    live_value = "dependency-source-live-value-1234567890"
    _write(
        source,
        "process-plan-agent-ui/node_modules/example/index.js",
        f'const {key_name} = "{live_value}";\n',
    )

    result = _stage(source, destination)

    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "non-placeholder secret" in output
    assert "index.js" in output
    assert live_value not in output


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is required for the Windows packager")
def test_stage_fails_when_pem_contains_private_key_material(tmp_path: Path):
    source = tmp_path / "source"
    destination = tmp_path / "stage"
    private_key_header = "-----BEGIN " + "PRIVATE KEY-----"
    private_key_footer = "-----END " + "PRIVATE KEY-----"
    _write(
        source,
        "process-plan-agent-api/deployment.pem",
        f"{private_key_header}\nprivate-material-must-not-ship\n{private_key_footer}\n",
    )

    result = _stage(source, destination)

    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "private key material" in output
    assert "deployment.pem" in output
    assert "private-material-must-not-ship" not in output


@pytest.mark.skipif(
    POWERSHELL is None or os.name != "nt",
    reason="Windows PowerShell and reparse-point support are required",
)
def test_stage_refuses_file_reparse_points(tmp_path: Path):
    source = tmp_path / "source"
    destination = tmp_path / "stage"
    external = _write(tmp_path, "external.txt", "fixture external content")
    link = source / "scripts" / "linked.txt"
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(external)
    except OSError as exc:
        pytest.skip(f"File symlinks are unavailable: {exc}")

    result = _stage(source, destination)

    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "reparse point" in output
    assert "scripts/linked.txt" in output.replace("\\", "/")
