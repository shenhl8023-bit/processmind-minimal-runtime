"""Build immutable ZIP archives from persisted finalized V2 packages."""

from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from app.models.models import FinalizedRulePackage
from app.services.finalized_rule_package_helpers import json_loads
from app.services.rule_packages.kmai_export import (
    KMAI_TARGET_DIRECTORY,
    build_kmai_compatibility_export,
)
from app.services.rule_packages.lifecycle import (
    RulePackageLifecycleError,
    load_legacy_mapping_snapshot_for_package,
    v2_package_from_row,
)


class RulePackageArchiveError(ValueError):
    """Raised when a persisted package cannot produce a complete archive."""


@dataclass(frozen=True)
class RulePackageArchive:
    filename: str
    content: bytes


_FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def _archive_filename(row: FinalizedRulePackage) -> str:
    package_name = str(row.package_name or "process_route_rules").strip()
    safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", package_name).strip(" ._")
    return f"{safe_name or 'process_route_rules'}_v{int(row.version or 1)}.zip"


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")


def _write_file(archive: zipfile.ZipFile, name: str, content: bytes) -> None:
    info = zipfile.ZipInfo(name, _FIXED_ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, content)


def _manual_boolean_factors(files: dict[str, dict[str, Any]]) -> list[tuple[str, str]]:
    factors = files.get("factor_schema.json", {}).get("factors", [])
    return [
        (str(item["factor_key"]), str(item.get("name") or item["factor_key"]))
        for item in factors
        if isinstance(item, dict)
        and item.get("source_mode") == "manual_override"
        and item.get("value_type") == "boolean"
        and item.get("factor_key")
    ]


def _readme_text(files: dict[str, dict[str, Any]]) -> str:
    manual_lines = [
        f"- {key}: {name}" for key, name in _manual_boolean_factors(files)
    ] or ["- None"]
    return "\n".join(
        [
            "KmAI 规则文件替换说明",
            "",
            f"目标目录：{KMAI_TARGET_DIRECTORY}",
            "",
            "1. 先停止 KmAI Agent。",
            "2. 备份目标目录中同名的四个 JSON 文件。",
            "3. 将本目录中的 factor_schema.json、factor_expansion_rules.json、route_catalog.json、route_rules.json 复制到目标目录并覆盖。",
            "4. 不要删除或覆盖原有 group_match_rules.json。",
            "5. 重新启动 KmAI Agent；后续工艺路线生成将使用本次导出的 ProcessMind 规则。",
            "6. route_catalog.json 的 template_group_aliases 为 ProcessMind 附加元数据；KmAI v1 会忽略它，不影响路线生成。",
            "",
            "Manual boolean factors require manual.factor_overrides values (true/false):",
            *manual_lines,
            "",
        ]
    )


def build_finalized_rule_package_archive(
    row: FinalizedRulePackage,
) -> RulePackageArchive:
    """Create a deterministic ZIP from one persisted finalized-package row."""

    try:
        package = v2_package_from_row(row)
        legacy_mapping_snapshot = load_legacy_mapping_snapshot_for_package(row)
        kmai_export = build_kmai_compatibility_export(
            package,
            legacy_mapping_snapshot=legacy_mapping_snapshot,
        )
    except (RulePackageLifecycleError, ValueError, TypeError, KeyError) as exc:
        raise RulePackageArchiveError(f"无法从持久化 V2 规则包生成归档：{exc}") from exc

    if not kmai_export.valid:
        details = "; ".join(issue.message for issue in kmai_export.errors)
        raise RulePackageArchiveError(
            f"持久化 V2 规则包无法生成有效的 KmAI 文件：{details or '未知错误'}"
        )

    root_files: tuple[tuple[str, bytes], ...] = (
        ("manifest.json", _json_bytes(package.manifest.model_dump(mode="json"))),
        ("input_schema.json", _json_bytes(package.input_schema.model_dump(mode="json"))),
        ("route_catalog.json", _json_bytes(package.route_catalog.model_dump(mode="json"))),
        ("route_rules.json", _json_bytes(package.route_rules.model_dump(mode="json"))),
        ("test_cases.json", _json_bytes([case.model_dump(mode="json") for case in package.test_cases])),
        ("rule_report.md", (row.rule_report_md or "").encode("utf-8")),
        ("validation_report.json", _json_bytes(json_loads(row.validation_report_json))),
    )
    required_kmai_files = (
        "factor_schema.json",
        "factor_expansion_rules.json",
        "route_catalog.json",
        "route_rules.json",
    )
    missing_kmai_files = [
        name for name in required_kmai_files if name not in kmai_export.files
    ]
    if missing_kmai_files:
        raise RulePackageArchiveError(
            "KmAI compatibility export is missing required file(s): "
            + ", ".join(missing_kmai_files)
        )
    kmai_files = tuple(
        (f"kmai-v1/{name}", _json_bytes(kmai_export.files[name]))
        for name in required_kmai_files
    )

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as archive:
        for name, content in root_files:
            _write_file(archive, name, content)
        for name, content in kmai_files:
            _write_file(archive, name, content)
        _write_file(
            archive,
            "kmai-v1/README-替换说明.txt",
            _readme_text(kmai_export.files).encode("utf-8"),
        )

    return RulePackageArchive(filename=_archive_filename(row), content=buffer.getvalue())
