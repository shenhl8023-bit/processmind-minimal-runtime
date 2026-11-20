"""Clean full release using the verified, unchanged Windows runtime."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import runpy
import shutil
import stat
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[4]
RELEASE = "full-template-20261120-pm092"
BASE = ROOT / "dist-win7/processmind-win7-full-template-20261108.zip"
STAGE = ROOT / ("dist-win7/processmind-win7-" + RELEASE)
ARCHIVE = STAGE.with_suffix(".zip")
EVIDENCE = Path(__file__).resolve().parent
VERIFIER = runpy.run_path(str(ROOT / "scripts/verify-win7-package.py"))


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def excluded(rel):
    parts = {part.lower() for part in rel.parts}
    return (VERIFIER["_is_forbidden"](rel.as_posix()) or bool(parts & {
        ".venv", ".git", ".scratch", ".runtime", "tests", "node_modules", "outputs", "output", "__pycache__",
        ".pytest_cache", ".mypy_cache", ".ruff_cache", ".ds_store", "thumbs.db", "desktop.ini",
    }) or rel.name.lower().startswith(("credentials", "secrets", "tokens")))


def copy_file(relative):
    source = ROOT / relative
    if source.is_symlink() or not source.is_file():
        raise RuntimeError("Missing or unsafe release source: " + str(relative))
    target = STAGE / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def copy_tree(relative):
    for directory, folders, files in os.walk(ROOT / relative, followlinks=False):
        for name in folders + files:
            if (Path(directory) / name).is_symlink():
                raise RuntimeError("Refusing release symlink: " + str(Path(directory) / name))
        folders[:] = [name for name in folders if not excluded((Path(directory) / name).relative_to(ROOT))]
        for name in files:
            rel = (Path(directory) / name).relative_to(ROOT)
            if not excluded(rel):
                copy_file(rel)


def checksums():
    file = STAGE / "SHA256SUMS.txt"
    file.write_text("".join(sha256(p) + "  " + p.relative_to(STAGE).as_posix() + "\n"
                             for p in sorted(STAGE.rglob("*")) if p.is_file() and p != file), encoding="utf-8")


def prepare():
    if STAGE.exists() or ARCHIVE.exists():
        raise RuntimeError("Refusing to overwrite release")
    expected = BASE.with_suffix(".zip.sha256").read_text().split()[0]
    if sha256(BASE) != expected:
        raise RuntimeError("Runtime source archive checksum mismatch")
    STAGE.mkdir()
    runtime_hashes = {}
    with zipfile.ZipFile(BASE) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("Runtime source archive CRC failed")
        recorded = dict(line.split("  ", 1)[::-1] for line in archive.read("SHA256SUMS.txt").decode("utf-8-sig").splitlines() if line.strip())
        for item in archive.infolist():
            path = PurePosixPath(item.filename)
            if path.is_absolute() or ".." in path.parts or "\\" in item.filename or stat.S_ISLNK(item.external_attr >> 16):
                raise RuntimeError("Unsafe archive member")
            if item.is_dir() or not item.filename.startswith(".runtime/python/"):
                continue
            content = archive.read(item)
            digest = hashlib.sha256(content).hexdigest()
            if recorded.get(item.filename) != digest:
                raise RuntimeError("Runtime file checksum mismatch")
            target = STAGE / item.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            runtime_hashes[item.filename] = digest
    assert len(runtime_hashes) == 1967
    for directory in ("process-plan-agent-api", "process-plan-agent-ui/dist", "docs/配置模板", "prerequisites", "integrations/kmai"):
        copy_tree(directory)
    for name in ("start-win7.bat", "stop-win7.cmd", "status-win7.cmd", "launcher-config.json", "requirements-win7-py38.txt", ".env.example",
                 "product-profile.json", "product-features.json", "README.md", "docs/用户使用说明.md", "docs/deployment-features.md",
                 "docs/系统简介.md", "docs/Win7功能测试方案-20261025.md", "docs/Win7缺陷清单-20261025.md",
                 "scripts/win7_launcher.py", "scripts/validate-python38.py", "scripts/verify-win7-package.py"):
        copy_file(Path(name))
    guide = """ProcessMind 2026.11.20 完整版（Win7 SP1 x64）

1. 解压到新的空目录；不要覆盖旧包。
2. 首次部署先按 prerequisites/README.md 安装必要更新并重启。
3. 使用 Chrome 109 / Edge 109，双击 start-win7.bat；目标机不需要安装Node或Python。
4. 数据默认保存在 %LOCALAPPDATA%\\ProcessMind；启动器不会自动删除旧数据。备份/迁移请先关闭服务。
5. 在模型设置中配置客户自己的模型地址、模型名和Key；包内没有开发机数据或密钥。
6. 当前版只接收PDF工艺规程；第四步保存，第五步生成并检查路线后导出三表ZIP。
7. 包含完整分组模板导入、映射和编排能力，无试用到期限制。沿用当前隐藏界面的配置；如需第六步，将 product-features.json 的 template_mapping_enabled 改为 true，重启并刷新。
8. 本版修复特征参数条件必填导致的规则包导出失败，三个JSON文件保持不变；不需要重新回答或调整规则。
9. 接收系统需要配套更新读取器：参照 integrations/kmai/README.md，备份后替换对应脚本。其它电脑未自动更新。
10. 本版修复第三步问答未就绪时提前保存及误报必答未完成；模型空正文最多恢复一次，截断、拒绝、超时分别反馈，已答内容继续保留。
11. 完全关闭使用 stop-win7.cmd；状态检查使用 status-win7.cmd。

已完成自动回归和macOS隔离验收；仍需在Win7 SP1 x64实机验证启停、完整客户流程；本机真实模型连接与第三至第五步已验证，外部模型仍可能偶发超时。
"""
    (STAGE / "使用说明.txt").write_bytes(b"\xef\xbb\xbf" + guide.replace("\n", "\r\n").encode("utf-8"))
    source = {p.relative_to(STAGE).as_posix(): sha256(p) for p in sorted(STAGE.rglob("*")) if p.is_file() and not p.relative_to(STAGE).as_posix().startswith(".runtime/")}
    profile = json.loads((STAGE / "product-profile.json").read_text())
    assert profile == {"edition": "full", "template_mapping_enabled": True, "expires_at": None}
    manifest = {
        "package": "ProcessMind", "package_version": "2026.11.20", "release_id": RELEASE,
        "edition": "full", "trial_expires_at": None, "target_os": "Windows 7 SP1", "architecture": "x64",
        "python": "3.8.10", "frontend_target": "chrome109", "api": {"host": "127.0.0.1", "port": 8000},
        "launcher_config": "launcher-config.json", "browser_baseline": ["Chrome 109", "Edge 109"],
        "embedded_browser": False, "node_runtime_included": False,
        "windows_prerequisite": {"id": "KB2533623", "installer": "prerequisites/install-kb2533623.bat", "payload": "prerequisites/Windows6.1-KB2533623-x64.msu", "reboot_required": True},
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "checksum_file": "SHA256SUMS.txt",
        "source_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "working_tree_changes_included": False, "source_file_sha256": source, "build_host": "macOS",
        "win7_runtime_execution_verified_in_this_build": False,
        "runtime_provenance": {"package": BASE.name, "sha256": expected, "files": len(runtime_hashes), "unchanged": True},
        "automated_tests": {"backend_passed": 2294, "backend_skipped": 111, "frontend_passed": 1418, "frontend_skipped": 1, "frontend_build": "passed", "python38_source_check": "passed"},
        "export_format": "sample-three-arrays-with-stable-public-identities", "export_tables": ["factor_table.json", "full_route_table.json", "rule_table.json"],
        "conditional_input_validation": "factor.required_when", "companion_receiver": "integrations/kmai/config_route_engine.py",
        "release_status": "candidate-awaiting-native-win7-acceptance",
    }
    (STAGE / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    checksums()
    errors = VERIFIER["verify_package"](STAGE)
    if errors:
        raise RuntimeError("\n".join(errors))
    (EVIDENCE / "runtime-hashes.json").write_text(json.dumps(runtime_hashes, indent=2) + "\n")
    print(json.dumps({"stage": str(STAGE), "runtime_files": len(runtime_hashes), "source_files": len(source), "verification": "passed"}))


def seal():
    if ARCHIVE.exists():
        raise RuntimeError("Refusing to overwrite archive")
    errors = VERIFIER["verify_package"](STAGE)
    if errors:
        raise RuntimeError("\n".join(errors))
    # No development machine key may appear in text or generated frontend assets.
    secrets = set()
    for settings in (ROOT / "data/config/process_settings.json", ROOT / "process-plan-agent-api/process_settings.json"):
        if settings.exists():
            payload = json.loads(settings.read_text())
            rows = payload if isinstance(payload, list) else []
            secrets.update(str(row.get("value", "")) for row in rows if isinstance(row, dict) and row.get("key") in {"LLM_API_KEY", "OPENAI_API_KEY", "KNOWLEDGE_SEARCH_API_KEY"} and len(str(row.get("value", ""))) >= 12)
    for p in STAGE.rglob("*"):
        if not p.is_file() or p.relative_to(STAGE).as_posix().startswith(".runtime/"):
            continue
        data = p.read_bytes()
        if any(value.encode() in data for value in secrets):
            raise RuntimeError("Development credential found in staged artifact: " + p.relative_to(STAGE).as_posix())
        if p.suffix.lower() in {".json", ".md", ".txt", ".js", ".py", ".html"} and re.search(rb"\bsk-[A-Za-z0-9_-]{24,}\b", data):
            raise RuntimeError("Possible credential found in staged artifact: " + p.relative_to(STAGE).as_posix())
    with zipfile.ZipFile(ARCHIVE, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for p in sorted(STAGE.rglob("*")):
            if p.is_file():
                archive.write(p, p.relative_to(STAGE).as_posix())
    with zipfile.ZipFile(ARCHIVE) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("ZIP CRC failed")
        for p in STAGE.rglob("*"):
            if p.is_file() and hashlib.sha256(archive.read(p.relative_to(STAGE).as_posix())).hexdigest() != sha256(p):
                raise RuntimeError("ZIP file mismatch")
    digest = sha256(ARCHIVE)
    ARCHIVE.with_suffix(".zip.sha256").write_text(digest + "  " + ARCHIVE.name + "\n")
    for name in ("manifest.json", "SHA256SUMS.txt"):
        shutil.copyfile(STAGE / name, ARCHIVE.with_suffix("." + name))
    evidence = {"archive": str(ARCHIVE), "bytes": ARCHIVE.stat().st_size, "sha256": digest, "files": len(zipfile.ZipFile(ARCHIVE).namelist()), "verified": True}
    (EVIDENCE / "package-verification.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(evidence, ensure_ascii=False))


if __name__ == "__main__":
    {"prepare": prepare, "seal": seal}[sys.argv[1]]()
