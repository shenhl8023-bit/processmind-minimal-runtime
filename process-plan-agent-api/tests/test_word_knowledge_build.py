"""Protect source grounding and offline rebuild, rather than generated row counts."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("word-knowledge")
    result = subprocess.run([sys.executable, str(ROOT / "scripts/build_word_knowledge.py"), "--output", str(out)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    return {name: json.loads((out / f"word_{name}.json").read_text()) for name in ("records", "sources", "issues", "coverage")}


def test_offline_build_covers_eight_originals_and_every_anchor(built):
    ids = [r["id"] for r in built["records"]]
    assert len(ids) == len(set(ids))
    assert {s["id"] for s in built["sources"]} == {f"WD{i:02}" for i in range(1, 9)}
    for s in built["sources"]:
        path = ROOT / s["source_path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == s["sha256"]
    routes = [r for r in built["records"] if r["category"] == "typical_route"]
    assert len(routes) == 9  # WD03 keeps the text overview and conflicting figure sequence separately.
    assert {r["source"]["document_id"] for r in routes} == {f"WD{i:02}" for i in range(1, 9)}
    for source in built["sources"]:
        rows = [c for c in built["coverage"] if c["source_id"] == source["id"]]
        assert any(c["anchor"] == "P001" for c in rows)
        assert any(c["anchor"].endswith(".png") for c in rows)
        assert all(c["record_ids"] or c["reason"] for c in rows)
    assert all(r["source"]["page_no"] is None for r in built["records"])


def test_allowances_are_editable_single_metrics_with_source_basis(built):
    rows = [r for r in built["records"] if r["guidance"]["kind"] == "allowance"]
    assert rows
    assert all(len(r["guidance"]["metrics"]) == 1 for r in rows)
    hard_bore = [r for r in rows if r["source"]["document_id"] == "WD05"]
    assert {(m["min"], m["max"]) for r in hard_bore for m in r["guidance"]["metrics"]} >= {(0.01, 0.02), (0, 0.005)}
    assert all(r["guidance"]["conditions"] and r["guidance"]["exceptions"] for r in rows)


def test_tempering_conflict_is_preserved_on_both_sides(built):
    members = [r for r in built["records"] if "WD01-tempering-hardness" in r.get("conflict_ids", [])]
    values = {(m["min"], m["max"]) for r in members for m in r["guidance"].get("metrics", [])}
    assert values == {(22, 32), (27, 35)}
    assert all(r["guidance"]["verification_status"] == "conflict" for r in members)
    assert any("image3.png" in r["source"]["identity"] for r in members)


def test_resources_are_image_grounded_and_not_generic_capabilities(built):
    rows = [r for r in built["records"] if r["guidance"]["kind"] == "resource"]
    models = {x["model"] for r in rows for x in r["guidance"]["resources"]}
    assert {"Z512", "MC1805", "S21"} <= models
    assert any(x["category"] == "gauge" for r in rows for x in r["guidance"]["resources"])
    assert all("image" in r["source"]["identity"] for r in rows)
    assert all("示例" in r["guidance"]["conditions"] for r in rows)


def test_formula_semantics_and_virtual_trial_keep_exceptions(built):
    records = built["records"]
    formulas = [r for r in records if r["guidance"]["kind"] == "formula"]
    assert any("(镀前内孔尺寸-镀后内孔最终尺寸)/2" in r["guidance"]["conclusion"] for r in formulas)
    assert all(r["guidance"]["exceptions"] for r in formulas)
    assert all(not r["guidance"].get("metrics") for r in formulas)
    assert all(any(token in r["guidance"]["conclusion"] for token in ("=", "公式", "厚度")) for r in formulas)
    trials = [r for r in records if r["source"]["document_id"] == "WD03" and "低温灵活性试验" in r["guidance"]["topics"]]
    assert any("无低温灵活性试验要求" in r["guidance"]["conclusion"] for r in trials)
    assert next(r for r in records if r["id"].startswith("WD03-") and r["category"] == "typical_route")["guidance"]["completeness"] == "stage_overview"


def test_suspicious_steel_values_link_pending_issue_and_routes_expose_condition_status(built):
    issues = {issue["id"]: issue for issue in built["issues"]}
    numeric = issues["WD01-numeric"]
    linked = [r for r in built["records"] if "WD01-numeric" in r.get("issue_ids", [])]
    assert len(linked) == 2
    assert {"WD01-numeric"} <= {issue for r in linked for issue in r.get("issue_ids", [])}
    assert {r["id"] for r in linked} <= set(numeric["record_ids"])
    routes = [r for r in built["records"] if r["category"] == "typical_route"]
    statuses = {op["execution_status"] for r in routes for op in r["guidance"]["operations"]}
    assert {"required", "conditional", "virtual"} <= statuses
    assert all(op["source"]["identity"] and op["source"]["page_no"] is None for r in routes for op in r["guidance"]["operations"])


def test_legible_diagrams_are_transcribed_in_arrow_order_with_repeats(built):
    routes = {r["source"]["document_id"]: r for r in built["records"] if r["category"] == "typical_route"}
    for source_id in ("WD02", "WD05", "WD06", "WD07", "WD08"):
        assert routes[source_id]["guidance"]["completeness"] == "verified_sequence"
        expected_status = "conflict" if source_id in ("WD05", "WD08") else "verified"
        assert routes[source_id]["guidance"]["verification_status"] == expected_status
        assert all("image2.png" in op["source"]["identity"] for op in routes[source_id]["guidance"]["operations"])
        assert all(op["number"] == "" for op in routes[source_id]["guidance"]["operations"])
    assert [op["name"] for op in routes["WD02"]["guidance"]["operations"]].count("车外圆") == 2
    assert any(op["name"] == "磨槽" and op["execution_status"] == "virtual" for op in routes["WD02"]["guidance"]["operations"])
    assert any(op["name"] == "去应力" and op["execution_status"] == "virtual" for op in routes["WD06"]["guidance"]["operations"])
    assert next(r for r in built["records"] if r["category"] == "typical_route" and r["source"]["document_id"] == "WD03" and r["guidance"]["kind"] == "stage_overview")["guidance"]["completeness"] == "stage_overview"
    assert all(routes[source_id]["guidance"]["completeness"] == "stage_overview" for source_id in ("WD01", "WD04"))
    assert any(r["source"]["document_id"] == "WD03" and r["source"]["identity"].endswith("image2.png") and r["guidance"]["verification_status"] == "conflict" for r in [r for r in built["records"] if r["category"] == "typical_route"])


def test_wd03_diagram_keeps_nineteen_nodes_and_links_both_route_conflicts(built):
    routes = [r for r in built["records"] if r["category"] == "typical_route" and r["source"]["document_id"] == "WD03"]
    diagram = next(r for r in routes if r["source"]["identity"].endswith("image2.png"))
    overview = next(r for r in routes if r["guidance"]["kind"] == "stage_overview")
    assert len(diagram["guidance"]["operations"]) == 19
    assert [op["sequence"] for op in diagram["guidance"]["operations"]] == list(range(1, 20))
    assert all(op["number"] == "" for op in diagram["guidance"]["operations"])
    assert {"WD03-route", "WD03-route-order"} <= set(diagram["conflict_ids"])
    assert "WD03-route" in overview["conflict_ids"]
    issues = {issue["id"]: issue for issue in built["issues"]}
    assert {diagram["id"], overview["id"]} <= set(issues["WD03-route"]["record_ids"])
