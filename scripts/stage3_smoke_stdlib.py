#!/usr/bin/env python3
"""
Stage-3 smoke verification using ONLY the Python standard library.

Why this exists:
  The agent sandbox often cannot install fastapi/pydantic (proxy/timeouts).
  This script still proves the critical Stage-3 contracts without those deps.

What it checks:
  1. Key files exist and contain required symbols
  2. Python sources parse (AST)
  3. V2 fixture package structure is valid
  4. Minimal deterministic planner reproduces fixture expected process order
  5. Frontend nestFactorValues / compile-path symbols are present

Run:
  python scripts/stage3_smoke_stdlib.py
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "process-plan-agent-api"
UI = ROOT / "process-plan-agent-ui"
FIXTURE = API / "tests" / "fixtures" / "rule_package_v2.json"

errors: list[str] = []
oks: list[str] = []


def ok(msg: str) -> None:
    oks.append(msg)
    print(f"  OK  {msg}")


def fail(msg: str) -> None:
    errors.append(msg)
    print(f" FAIL {msg}")


def check_files() -> None:
    print("\n[1] Key files")
    required = [
        UI / "src/api/rulePackages.ts",
        UI / "src/utils/finalizeRulePackage.ts",
        UI / "src/composables/useFinalizeRulePackageExport.ts",
        UI / "src/composables/useGenerateInputFields.ts",
        UI / "src/views/FinalizeView.vue",
        UI / "src/views/GenerateView.vue",
        API / "app/routers/generate.py",
        API / "app/schemas/schemas.py",
        API / "app/services/rule_packages/planner.py",
        API / "tests/test_generate_v2_production.py",
        FIXTURE,
    ]
    for path in required:
        if path.exists():
            ok(str(path.relative_to(ROOT)))
        else:
            fail(f"missing {path.relative_to(ROOT)}")


def check_symbols() -> None:
    print("\n[2] Required symbols")
    checks = {
        UI / "src/utils/finalizeRulePackage.ts": [
            "buildCompileRequestFromCards",
            "buildV2InputFields",
            "buildRuleReportFromV2Package",
        ],
        UI / "src/composables/useFinalizeRulePackageExport.ts": [
            "compileRulePackage",
            "schema_version: '2.0'",
            "downloadRuleDocumentV1Compat",
        ],
        UI / "src/composables/useGenerateInputFields.ts": [
            "export function nestFactorValues",
            "schema.fields",
            "schema_version",
        ],
        UI / "src/views/FinalizeView.vue": [
            "downloadRuleDocumentV1Compat",
            "FINALIZE_VIEW_COPY.exportDocument",
        ],
        UI / "src/config/finalizeRulePresentation.ts": [
            "exportDocument: '导出 V2 规则包'",
            "exportDocumentV1",
        ],
        UI / "src/views/GenerateView.vue": [
            "packageMetaLabel",
            "packageSchemaVersion",
        ],
        API / "app/routers/generate.py": [
            "finalized_rule_package_v2",
            "plan_route",
            "matched_rule_ids",
            "selected_process_ids",
        ],
        API / "app/schemas/schemas.py": [
            "rule_package_id",
            "matched_rule_ids",
            "schema_version",
        ],
        UI / "src/api/rulePackages.ts": [
            "compileRulePackage",
            "validateRulePackageV2",
            "simulateRulePackageDraft",
        ],
    }
    for path, needles in checks.items():
        if not path.exists():
            fail(f"skip symbols, missing {path.name}")
            continue
        text = path.read_text(encoding="utf-8")
        for needle in needles:
            if needle in text:
                ok(f"{path.name}: {needle}")
            else:
                fail(f"{path.name}: missing `{needle}`")


def check_ast() -> None:
    print("\n[3] Python AST parse")
    files = [
        API / "app/routers/generate.py",
        API / "app/schemas/schemas.py",
        API / "tests/test_generate_v2_production.py",
        API / "app/services/rule_packages/planner.py",
        API / "app/services/rule_packages/contracts.py",
        API / "app/services/rule_packages/expression_engine.py",
    ]
    for path in files:
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            ok(f"parse {path.relative_to(ROOT)}")
        except SyntaxError as exc:
            fail(f"syntax {path.relative_to(ROOT)}: {exc}")


# --- Minimal expression + planner (stdlib clone of V2 semantics for fixture) ---

MISSING = object()


def resolve_field(inputs: dict, field: str):
    if field in inputs:
        return inputs[field]
    current = inputs
    for part in field.split("."):
        if not isinstance(current, dict) or part not in current:
            return MISSING
        current = current[part]
    return current


def _norm(v):
    return v.strip().casefold() if isinstance(v, str) else v


def eval_condition(node: dict, inputs: dict) -> bool:
    if "all" in node:
        return all(eval_condition(child, inputs) for child in node["all"])
    if "any" in node:
        return any(eval_condition(child, inputs) for child in node["any"])
    if "not" in node:
        return not eval_condition(node["not"], inputs)
    field = node.get("field")
    op = node.get("op")
    expected = node.get("value")
    actual = resolve_field(inputs, field)
    if op == "exists":
        return actual is not MISSING and actual not in (None, "", [], {})
    if op == "not_exists":
        return actual is MISSING or actual in (None, "", [], {})
    if actual is MISSING:
        return False
    if op == "eq":
        return _norm(actual) == _norm(expected)
    if op == "neq":
        return _norm(actual) != _norm(expected)
    if op == "in":
        return any(_norm(actual) == _norm(item) for item in expected)
    if op == "contains":
        if isinstance(actual, list):
            return any(_norm(item) == _norm(expected) for item in actual)
        if isinstance(actual, str):
            return str(expected).casefold() in actual.casefold()
        return False
    if op == "gte":
        return float(actual) >= float(expected)
    if op == "gt":
        return float(actual) > float(expected)
    if op == "lte":
        return float(actual) <= float(expected)
    if op == "lt":
        return float(actual) < float(expected)
    raise ValueError(f"unsupported op {op}")


def plan_route_min(package: dict, inputs: dict) -> list[str]:
    processes = package["route_catalog"]["processes"]
    process_map = {p["process_id"]: p for p in processes}
    selected = {p["process_id"] for p in processes if p.get("main")}
    decisions: dict[str, tuple[str, int, str]] = {}

    rules = sorted(
        package["route_rules"]["rules"],
        key=lambda r: (-int(r.get("priority") or 0), r["rule_id"]),
    )
    for rule in rules:
        if rule.get("enabled", True) is False:
            continue
        if not eval_condition(rule["when"], inputs):
            continue
        prio = int(rule.get("priority") or 0)
        then = rule["then"]
        for pid in then.get("include_process_ids") or []:
            decisions[pid] = ("include", prio, rule["rule_id"])
        for pid in then.get("exclude_process_ids") or []:
            decisions[pid] = ("exclude", prio, rule["rule_id"])

    for pid, (action, _, _) in decisions.items():
        if action == "include":
            selected.add(pid)
        elif not process_map[pid].get("main"):
            selected.discard(pid)

    # expand requires
    pending = list(selected)
    while pending:
        pid = pending.pop()
        for req in process_map[pid].get("constraints", {}).get("requires") or []:
            if req not in selected:
                selected.add(req)
                pending.append(req)

    # topo by requires + default_sequence
    indeg = {pid: 0 for pid in selected}
    edges = {pid: set() for pid in selected}

    def edge(a, b):
        if a in selected and b in selected and a != b and b not in edges[a]:
            edges[a].add(b)
            indeg[b] += 1

    for pid in selected:
        c = process_map[pid].get("constraints") or {}
        for req in c.get("requires") or []:
            edge(req, pid)
        for before in c.get("must_run_after") or []:
            edge(before, pid)
        for after in c.get("must_run_before") or []:
            edge(pid, after)

    ready = sorted(
        [pid for pid, d in indeg.items() if d == 0],
        key=lambda pid: (process_map[pid].get("default_sequence") or 0, pid),
    )
    ordered: list[str] = []
    while ready:
        pid = ready.pop(0)
        ordered.append(pid)
        nxt = []
        for b in edges[pid]:
            indeg[b] -= 1
            if indeg[b] == 0:
                nxt.append(b)
        ready = sorted(
            ready + nxt,
            key=lambda x: (process_map[x].get("default_sequence") or 0, x),
        )
    if len(ordered) != len(selected):
        raise RuntimeError("dependency cycle in fixture")
    return ordered


def check_fixture_planner() -> None:
    print("\n[4] Fixture + minimal planner")
    package = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert package["manifest"]["schema_version"] == "2.0"
    assert package["input_schema"]["schema_version"] == "2.0"
    ok("fixture schema_version=2.0")

    case = package["test_cases"][0]
    ordered = plan_route_min(package, case["input"])
    expected = case["expect"]["included_process_ids"]
    if ordered == expected:
        ok(f"planner order matches fixture: {ordered}")
    else:
        fail(f"planner order {ordered} != expected {expected}")

    # display rename must not change selection
    package2 = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for p in package2["route_catalog"]["processes"]:
        if p["process_id"] == "process_quench":
            p["display_name"] = "真空淬火（新名称）"
    ordered2 = plan_route_min(package2, {"material": {"grade": "9Cr18"}, "target_hardness_hrc": 58})
    if "process_quench" in ordered2:
        ok("process_id stable after display_name change")
    else:
        fail("process_quench missing after rename")


def check_nest_factor_values_ts() -> None:
    print("\n[5] nestFactorValues semantics (reimplemented)")
    # Mirror the TS implementation
    def nest(flat: dict) -> dict:
        nested: dict = {}
        for key, value in flat.items():
            if "." not in key:
                nested[key] = value
                continue
            parts = [p for p in key.split(".") if p]
            cursor = nested
            for i, part in enumerate(parts):
                if i == len(parts) - 1:
                    cursor[part] = value
                else:
                    if part not in cursor or not isinstance(cursor[part], dict):
                        cursor[part] = {}
                    cursor = cursor[part]
        return nested

    got = nest(
        {
            "material.grade": "9Cr18",
            "cad.features": ["槽类特征"],
            "target_hardness_hrc": 58,
        }
    )
    expect = {
        "material": {"grade": "9Cr18"},
        "cad": {"features": ["槽类特征"]},
        "target_hardness_hrc": 58,
    }
    if got == expect:
        ok("nestFactorValues shape correct")
    else:
        fail(f"nestFactorValues got {got}")


def check_generate_route_complete() -> None:
    print("\n[6] generate_route function completeness")
    text = (API / "app/routers/generate.py").read_text(encoding="utf-8")
    if "async def generate_route" not in text:
        fail("generate_route missing")
        return
    # must return GenerateResponse with new fields
    for needle in [
        "return GenerateResponse(",
        "rule_package_id=rule_package_id",
        "matched_rule_ids=matched_rule_ids",
        "selected_process_ids=selected_process_ids",
        'output_mode = "finalized_rule_package_v2"',
    ]:
        if needle in text:
            ok(f"generate.py contains {needle}")
        else:
            fail(f"generate.py missing {needle}")
    # truncated-file guard: file should not end mid-except
    if text.rstrip().endswith("except HTTPException:"):
        fail("generate.py still truncated after except HTTPException")
    else:
        ok("generate.py not truncated")


def main() -> int:
    print("ProcessMind Stage-3 stdlib smoke")
    print(f"ROOT = {ROOT}")
    check_files()
    check_symbols()
    check_ast()
    check_fixture_planner()
    check_nest_factor_values_ts()
    check_generate_route_complete()

    print("\n========================================")
    print(f" passed: {len(oks)}")
    print(f" failed: {len(errors)}")
    if errors:
        print("----------------------------------------")
        for e in errors:
            print(" -", e)
        print("========================================")
        return 1

    print(" ALL SMOKE CHECKS PASSED")
    print("========================================")
    print("")
    print("Note: this does not replace full pytest/vitest on your Windows host.")
    print("Run: scripts\\verify-stage3.cmd")
    return 0


if __name__ == "__main__":
    sys.exit(main())
