import json
from types import SimpleNamespace

from app.services.finalized_route_generator import generate_steps_from_finalized_rule_package
from app.services.param_rule_expression import (
    matches_factor_condition,
    parse_factor_condition,
    to_bool,
    to_float,
)


def test_v1_rule_package_behavior_baseline():
    catalog = {
        "segments": [
            {"process_id": "prepare", "sequence": 10, "process_name": "准备", "main": True, "primary_steps": ["清理"], "attached_steps": []},
            {"process_id": "quench", "sequence": 20, "process_name": "淬火", "main": False, "primary_steps": ["装炉"], "attached_steps": ["记录温度"]},
            {"process_id": "mill_slot", "sequence": 30, "process_name": "铣槽", "main": False, "primary_steps": ["铣削"], "attached_steps": []},
            {"process_id": "grind_hole", "sequence": 40, "process_name": "磨孔", "main": False, "primary_steps": ["磨削内孔"], "attached_steps": []},
            {"process_id": "mark", "sequence": 50, "process_name": "标记", "main": False, "primary_steps": ["标印"], "attached_steps": []},
        ]
    }
    rules = {
        "material_rules": [{"when": {"material_grade": "9Cr18"}, "then": ["淬火"]}],
        "feature_rules": [{"when": {"cad_feature": "槽类特征"}, "then": ["铣槽"]}],
        "precision_rules": [{"when": {"precision_requirement": "孔精加工"}, "then": ["磨孔"]}],
        "special_requirement_rules": [{"when": {"special_requirement": "追溯标印"}, "then": ["标记"]}],
        "process_trigger_rules": [],
    }
    package = SimpleNamespace(
        version=3,
        route_catalog_json=json.dumps(catalog, ensure_ascii=False),
        route_rules_json=json.dumps(rules, ensure_ascii=False),
    )

    result = generate_steps_from_finalized_rule_package(
        package,
        {
            "material_grade": "9Cr18",
            "cad_features": ["槽类特征"],
            "precision_grades": ["孔精加工"],
            "special_requirements": ["追溯标印"],
        },
        collapse_quality_gates=lambda steps: steps,
        parse_factor_condition=parse_factor_condition,
        matches_factor_condition=matches_factor_condition,
        to_bool=to_bool,
        to_float=to_float,
    )

    assert result is not None
    steps, summary = result
    assert [step.process_id for step in steps] == ["prepare", "quench", "mill_slot", "grind_hole", "mark"]
    assert steps[1].process_steps == ["装炉", "记录温度"]
    assert summary == "已基于第4步规则包 V3 生成路线"
