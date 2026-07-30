import base64
import json
import shutil
import subprocess
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile

import pytest

from app.services.rule_packages.contracts import ProcessRelationV2
from app.services.rule_packages.kmai_compatibility_runner import compare_kmai_v1
from app.services.rule_packages.kmai_export import LegacyFactorAdapterEntry


PROJECT_ROOT = Path(__file__).resolve().parents[2]
COMPATIBILITY_TOOL = PROJECT_ROOT / "process-plan-agent-ui" / "public" / "kmai-compatibility-test.html"


def _compatibility_tool_function(name: str) -> str:
    source = COMPATIBILITY_TOOL.read_text(encoding="utf-8")
    start = source.find(f"function {name}(")
    assert start >= 0, f"standalone compatibility tool is missing {name}"
    opening = source.find("{", start)
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise AssertionError(f"standalone compatibility tool has an incomplete {name}")


def _compatibility_fixture_zip(validation_report: dict | None) -> bytes:
    files = {
        "manifest.json": {"package_name": "offline snapshot fixture", "schema_version": "2.0"},
        "input_schema.json": {
            "schema_version": "2.0",
            "fields": [{"key": "cad.features", "label": "CAD features", "type": "multi_select", "required": False}],
        },
        "route_catalog.json": {"processes": []},
        "route_rules.json": {"rules": [], "process_relations": []},
        "kmai-v1/factor_schema.json": {
            "factors": [
                {"factor_key": "snapshot_factor", "value_type": "boolean", "default_value": False},
                {"factor_key": "has_slot_feature", "value_type": "boolean", "default_value": False},
                {"factor_key": "manual_bool", "name": "Manual bool", "source_mode": "manual_override", "value_type": "boolean", "default_value": False},
                {"factor_key": "manual_number", "name": "Manual number", "source_mode": "manual_override", "value_type": "number", "default_value": None},
                {"factor_key": "manual_integer", "name": "Manual integer", "source_mode": "manual_override", "value_type": "integer", "default_value": None},
                {"factor_key": "manual_enum", "name": "Manual enum", "source_mode": "manual_override", "value_type": "enum", "options": ["A", "B"], "default_value": None},
                {"factor_key": "manual_text", "name": "Manual text", "source_mode": "manual_override", "value_type": "text", "default_value": None},
            ]
        },
        "kmai-v1/route_catalog.json": {"processes": []},
        "kmai-v1/route_rules.json": {"rules": []},
    }
    if validation_report is not None:
        files["validation_report.json"] = validation_report
    archive = BytesIO()
    with ZipFile(archive, "w", compression=ZIP_STORED) as output:
        for path, payload in files.items():
            output.writestr(path, json.dumps(payload, ensure_ascii=False))
    return archive.getvalue()


def _run_standalone_compatibility_page(tmp_path: Path, zip_bytes: bytes, inputs: dict) -> dict:
    source = COMPATIBILITY_TOOL.read_text(encoding="utf-8")
    hook = "      globalThis.__kmaiTest = { loaded: () => loaded, inputFields, buildV1Factors, dom };\n    })()"
    assert source.endswith("    })()\n  </script>\n</body>\n</html>\n")
    instrumented = source.replace("    })()\n  </script>", hook + "\n  </script>", 1)
    node_program = "\n".join(
        [
            "(async () => {",
            "class Element {",
            "  constructor(id) { this.id = id; this.listeners = {}; this.children = []; this.style = {}; this.className = ''; this.textContent = ''; this.innerHTML = ''; this.disabled = false; this.classList = { values: new Set(), add: (...names) => names.forEach((name) => this.classList.values.add(name)), remove: (...names) => names.forEach((name) => this.classList.values.delete(name)) }; }",
            "  addEventListener(name, callback) { this.listeners[name] = callback; }",
            "  async fire(name, event) { return await this.listeners[name](event); }",
            "  append(...nodes) { this.children.push(...nodes); }",
            "  appendChild(node) { this.children.push(node); return node; }",
            "  click() {}",
            "}",
            "const elements = {};",
            "globalThis.document = { getElementById: (id) => elements[id] || (elements[id] = new Element(id)), createElement: (tag) => new Element(tag), body: new Element('body') };",
            f"const pageSource = {json.dumps(instrumented)};",
            "eval(pageSource.match(/<script>([\\s\\S]*)<\\/script>/)[1]);",
            f"const archive = Buffer.from({json.dumps(base64.b64encode(zip_bytes).decode('ascii'))}, 'base64');",
            "const buffer = archive.buffer.slice(archive.byteOffset, archive.byteOffset + archive.byteLength);",
            "await elements.fileInput.fire('change', { target: { files: [{ name: 'fixture.zip', arrayBuffer: async () => buffer }] } });",
            "const testPage = globalThis.__kmaiTest;",
            f"const inputs = {json.dumps(inputs)};",
            "let factors = null; let error = null;",
            "try { factors = testPage.buildV1Factors(inputs); } catch (caught) { error = caught.message; }",
            "console.log(JSON.stringify({ loaded: Boolean(testPage.loaded()), validationReport: testPage.loaded() && testPage.loaded().validationReport, manualFields: testPage.loaded() ? testPage.inputFields().filter((field) => field.manualOverride).map((field) => field.key) : [], factors, error, importMessage: elements.importMessage.textContent }));",
            "})().catch((error) => { console.error(error); process.exitCode = 1 })",
        ]
    )
    script_path = tmp_path / "standalone-compatibility-page.cjs"
    script_path.write_text(node_program, encoding="utf-8")
    result = subprocess.run(
        ["node", str(script_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required to exercise the standalone compatibility tool")
def test_standalone_page_imports_zip_snapshots_normalizes_values_and_types_manual_overrides(tmp_path: Path):
    published_report = {
        "kmai_compatibility": {
            "mapping_snapshot": [
                {
                    "mapping_identity": "project:8",
                    "scope": "project",
                    "source_field": "cad.features",
                    "source_value": "　Ｆｅａｔｕｒｅ　　Ａ　",
                    "mapping_mode": "existing_factor",
                    "target_factor_key": "snapshot_factor",
                }
            ]
        }
    }
    published = _run_standalone_compatibility_page(
        tmp_path,
        _compatibility_fixture_zip(published_report),
        {
            "cad": {"features": [" Feature   A "]},
            "manual": {"factor_overrides": {"manual_bool": True, "manual_number": "12.5", "manual_integer": "7", "manual_enum": "B", "manual_text": "operator note"}},
        },
    )
    empty_snapshot = _run_standalone_compatibility_page(
        tmp_path,
        _compatibility_fixture_zip({"kmai_compatibility": {"mapping_snapshot": []}}),
        {"cad": {"features": ["槽类特征"]}, "manual": {"factor_overrides": {}}},
    )
    legacy_without_snapshot = _run_standalone_compatibility_page(
        tmp_path,
        _compatibility_fixture_zip(None),
        {"cad": {"features": ["槽类特征"]}, "manual": {"factor_overrides": {}}},
    )
    legacy_report_without_mapping_metadata = _run_standalone_compatibility_page(
        tmp_path,
        _compatibility_fixture_zip({"valid": True}),
        {"cad": {"features": ["槽类特征"]}, "manual": {"factor_overrides": {}}},
    )
    modern_report_without_snapshot = _run_standalone_compatibility_page(
        tmp_path,
        _compatibility_fixture_zip({"kmai_compatibility": {"mapping_signature": "published-mappings-v1"}}),
        {"cad": {"features": ["槽类特征"]}},
    )
    non_array_snapshot = _run_standalone_compatibility_page(
        tmp_path,
        _compatibility_fixture_zip({"kmai_compatibility": {"mapping_snapshot": {}}}),
        {"cad": {"features": ["槽类特征"]}},
    )
    invalid_number = _run_standalone_compatibility_page(
        tmp_path,
        _compatibility_fixture_zip(published_report),
        {"manual": {"factor_overrides": {"manual_number": "not-a-number"}}},
    )

    assert published["loaded"] is True
    assert published["validationReport"] == published_report
    assert published["manualFields"] == [
        "manual.factor_overrides.manual_bool",
        "manual.factor_overrides.manual_number",
        "manual.factor_overrides.manual_integer",
        "manual.factor_overrides.manual_enum",
        "manual.factor_overrides.manual_text",
    ]
    assert published["factors"] == {
        "snapshot_factor": True,
        "has_slot_feature": False,
        "manual_bool": True,
        "manual_number": 12.5,
        "manual_integer": 7,
        "manual_enum": "B",
        "manual_text": "operator note",
    }
    assert empty_snapshot["factors"]["has_slot_feature"] is False
    assert empty_snapshot["factors"]["manual_bool"] is False
    assert legacy_without_snapshot["factors"]["has_slot_feature"] is True
    assert legacy_report_without_mapping_metadata["loaded"] is True
    assert legacy_report_without_mapping_metadata["factors"]["has_slot_feature"] is True
    assert modern_report_without_snapshot["loaded"] is False
    assert "mapping_snapshot" in modern_report_without_snapshot["importMessage"]
    assert non_array_snapshot["loaded"] is False
    assert "mapping_snapshot" in non_array_snapshot["importMessage"]
    assert invalid_number["error"] == "manual override manual_number must be a valid number"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required to exercise the standalone compatibility tool")
def test_standalone_compatibility_tool_uses_published_mapping_snapshot_and_explicit_manual_overrides():
    normalize = _compatibility_tool_function("normalizeMappingValue")
    resolve = _compatibility_tool_function("resolveMappingSnapshots")
    translate = _compatibility_tool_function("translateMappedInputFactors")
    coerce_override = _compatibility_tool_function("coerceManualOverride")
    apply_overrides = _compatibility_tool_function("applyManualFactorOverrides")
    validation_report = {
        "kmai_compatibility": {
            "mapping_snapshot": [
                {
                    "mapping_identity": "project:8",
                    "scope": "project",
                    "source_field": "cad.features",
                    "source_value": "published snapshot feature",
                    "mapping_mode": "existing_factor",
                    "target_factor_key": "project_snapshot_factor",
                },
                {
                    "mapping_identity": "project:9",
                    "scope": "project",
                    "source_field": "cad.features",
                    "source_value": "manual slot feature",
                    "mapping_mode": "manual_factor",
                    "target_factor_key": "processmind_manual_slot",
                },
            ]
        }
    }
    node_program = "\n".join(
        [
            f"const normalizeMappingValue = ({normalize});",
            f"const resolveMappingSnapshots = ({resolve});",
            f"const translateMappedInputFactors = ({translate});",
            f"const coerceManualOverride = ({coerce_override});",
            f"const applyManualFactorOverrides = ({apply_overrides});",
            f"const validationReport = {json.dumps(validation_report)};",
            "const factors = translateMappedInputFactors(validationReport, { 'cad.features': ['published snapshot feature', 'manual slot feature'] });",
            "applyManualFactorOverrides(factors, [",
            "  { factor_key: 'processmind_manual_slot', source_mode: 'manual_override', value_type: 'boolean', default_value: false },",
            "  { factor_key: 'project_snapshot_factor', source_mode: 'catalog', value_type: 'boolean', default_value: false }",
            "], { processmind_manual_slot: true, project_snapshot_factor: false });",
            "console.log(JSON.stringify(factors));",
        ]
    )

    result = subprocess.run(
        ["node", "-e", node_program],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "project_snapshot_factor": True,
        "processmind_manual_slot": True,
    }


def test_kmai_compatibility_runner_compares_v2_and_v1(rule_package_v2):
    result = compare_kmai_v1(
        rule_package_v2,
        {
            "material": {"grade": "9Cr18"},
            "cad": {"features": ["槽类特征"]},
            "target_hardness_hrc": 58,
        },
    )

    assert result["errors"] == []
    assert "process_prepare" in result["v2_process_ids"]
    assert "process_prepare" in result["kmai_process_ids"]
    assert "material.9cr18.quench" in result["v2_matched_rule_ids"]


def test_kmai_compatibility_runner_reports_relation_gap(rule_package_v2):
    package = rule_package_v2.model_copy(deep=True)
    package.route_rules.process_relations.append(ProcessRelationV2(
        relation_id="test-relation",
        relation_type="order_after",
        source_process_ids=["process_prepare"],
        target_process_ids=["process_quench"],
        source="user_confirmed",
        source_segment_id="segment-1",
        source_text="淬火必须在准备之后",
        confirmed_by="tester",
        confirmed_at="2026-07-23T00:00:00Z",
    ))
    result = compare_kmai_v1(
        package,
        {
            "material": {"grade": "9Cr18"},
            "cad": {"features": ["槽类特征"]},
            "target_hardness_hrc": 58,
        },
    )

    assert result["semantic_gaps"]


def _legacy_manual_slot(rule_package_v2, factor_key="processmind_manual_slot"):
    package = rule_package_v2.model_copy(deep=True)
    package.route_rules.rules[1].when.factor_id = None
    return package, LegacyFactorAdapterEntry(
        source_field="cad.features",
        source_value="\u69fd\u7c7b\u7279\u5f81",
        mapping_mode="manual_factor",
        target_factor_key=factor_key,
        target_factor_name="Manual slot",
        target_factor_category="custom",
    )


def test_kmai_compatibility_runner_requires_manual_override_for_historical_mapping(rule_package_v2):
    package, snapshot = _legacy_manual_slot(rule_package_v2)

    result = compare_kmai_v1(
        package,
        {
            "material": {"grade": "9Cr18"},
            "cad": {"features": ["\u69fd\u7c7b\u7279\u5f81"]},
            "target_hardness_hrc": 58,
        },
        legacy_mapping_snapshot=[snapshot],
    )

    assert result["manual_factors"]["processmind_manual_slot"] is False
    assert any("processmind_manual_slot" in gap for gap in result["semantic_gaps"])


def test_historical_manual_mapping_preserves_captured_factor_definition(
    rule_package_v2,
):
    package, snapshot = _legacy_manual_slot(rule_package_v2, "processmind_manual_spoofed")

    result = compare_kmai_v1(
        package,
        {
            "material": {"grade": "9Cr18"},
            "cad": {"features": ["\u69fd\u7c7b\u7279\u5f81"]},
            "special": {"requirements": ["clean room"]},
            "target_hardness_hrc": 58,
        },
        legacy_mapping_snapshot=[snapshot],
    )

    assert result["manual_factors"]["processmind_manual_spoofed"] is False
    assert "feature.slot.mill" not in result["kmai_matched_rule_ids"]
    assert any("processmind_manual_spoofed" in gap for gap in result["semantic_gaps"])


def test_kmai_compatibility_runner_applies_historical_manual_override(rule_package_v2):
    package, snapshot = _legacy_manual_slot(rule_package_v2)

    result = compare_kmai_v1(
        package,
        {
            "material": {"grade": "9Cr18"},
            "cad": {"features": ["\u69fd\u7c7b\u7279\u5f81"]},
            "target_hardness_hrc": 58,
            "manual": {"factor_overrides": {"processmind_manual_slot": True}},
        },
        legacy_mapping_snapshot=[snapshot],
    )

    assert result["manual_factors"]["processmind_manual_slot"] is True
    assert "feature.slot.mill" in result["kmai_matched_rule_ids"]
    assert not any("processmind_manual_slot" in gap for gap in result["semantic_gaps"])


@pytest.mark.parametrize(
    "invalid_override",
    [pytest.param(1, id="number"), pytest.param("true", id="string")],
)
def test_boolean_manual_factor_rejects_non_boolean_override_before_simulation(
    rule_package_v2,
    invalid_override,
):
    package, snapshot = _legacy_manual_slot(rule_package_v2)

    result = compare_kmai_v1(
        package,
        {
            "material": {"grade": "9Cr18"},
            "cad": {"features": ["\u69fd\u7c7b\u7279\u5f81"]},
            "target_hardness_hrc": 58,
            "manual": {"factor_overrides": {"processmind_manual_slot": invalid_override}},
        },
        legacy_mapping_snapshot=[snapshot],
    )

    assert result["manual_factors"]["processmind_manual_slot"] is False
    assert "feature.slot.mill" not in result["kmai_matched_rule_ids"]
    assert any(
        "processmind_manual_slot" in gap and "exact JSON boolean" in gap
        for gap in result["semantic_gaps"]
    )


def test_kmai_compatibility_runner_preserves_special_requirement_simulation(rule_package_v2):
    package = rule_package_v2.model_copy(deep=True)
    package.route_rules.rules[1].when.field = "special.requirements"
    package.route_rules.rules[1].when.op = "contains"
    package.route_rules.rules[1].when.value = "\u65e0\u635f\u68c0\u6d4b\u8981\u6c42"
    package.route_rules.rules[1].when.factor_id = "requirement.nondestructive_testing"
    result = compare_kmai_v1(
        package,
        {
            "material": {"grade": "9Cr18"},
            "special": {"requirements": ["\u65e0\u635f\u68c0\u6d4b\u8981\u6c42"]},
            "target_hardness_hrc": 58,
        },
    )

    assert "feature.slot.mill" in result["kmai_matched_rule_ids"]
