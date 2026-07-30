import pytest
from pydantic import ValidationError

import app.services.rule_packages.standard_factors as standard_factor_module
from app.services.rule_packages.contracts import ConditionNode
from app.services.rule_packages.standard_factors import (
    STANDARD_FACTOR_CATALOG_VERSION,
    bind_unambiguous_factor_ids,
    matching_standard_factors,
    normalize_factor_leaves,
    standard_factor_map,
    standard_factors,
    validate_factor_bindings,
)
from app.services.rule_packages.contracts import StandardFactorDefinition


def test_standard_catalog_keeps_hole_finish_distinct_from_center_through_hole():
    """Fails if either fixed KmAI target is changed or conflated."""
    factors = standard_factor_map()

    assert factors["precision.hole_finish"].kmai_factor_key == "has_hole_finish_machining"
    assert factors["feature.center_hole_location"].kmai_factor_key == "uses_center_hole_location"
    assert all(item.kmai_factor_key != "has_center_through_hole" for item in factors.values())


def test_condition_node_persists_factor_id_only_on_leaf():
    """Fails if a rule can attach standard-factor identity to logical structure."""
    leaf = ConditionNode.model_validate({
        "field": "cad.features",
        "op": "contains",
        "value": "顶尖孔",
        "factor_id": "feature.center_hole_location",
    })

    assert leaf.factor_id == "feature.center_hole_location"
    with pytest.raises(ValidationError, match="logical condition cannot carry factor_id"):
        ConditionNode.model_validate({"all": [leaf.model_dump(mode="json")], "factor_id": "invalid"})


def test_catalog_covers_all_current_scalar_fields_and_returns_independent_copies():
    """Fails if a scalar loses its stable factor or a caller can mutate the catalog."""
    expected_ids = {
        "measurement.outer_diameter_it",
        "measurement.inner_diameter_it",
        "measurement.dimension_it",
        "measurement.roughness_ra",
        "measurement.roundness_mm",
        "measurement.cylindricity_mm",
        "measurement.coaxiality_mm",
        "measurement.runout_mm",
        "measurement.position_mm",
        "measurement.flatness_mm",
        "measurement.perpendicularity_mm",
        "measurement.diameter_mm",
        "measurement.length_mm",
        "measurement.hardness_hrc",
    }

    factors = standard_factors()
    assert STANDARD_FACTOR_CATALOG_VERSION == "2026.11"
    assert expected_ids <= {factor.factor_id for factor in factors}
    assert all(
        factor.runtime_source == "manual_override"
        for factor in factors
        if factor.factor_id in expected_ids
    )
    factors[0].label = "caller mutation"
    assert standard_factors()[0].label == "材料牌号"


def test_legacy_hardness_alias_matches_but_catalog_selects_canonical_field():
    """Fails if compatibility rewrites the canonical standard-factor source."""
    legacy = ConditionNode(field="target_hardness_hrc", op="gte", value=55)

    assert [factor.factor_id for factor in matching_standard_factors(legacy)] == ["measurement.hardness_hrc"]
    factor = standard_factor_map()["measurement.hardness_hrc"]
    assert factor.source_field == "mechanical.hardness_hrc"
    assert factor.source_field_aliases == ["target_hardness_hrc"]


def test_multi_value_presence_leaf_is_split_before_binding():
    """Fails if a multi-value presence condition cannot be confirmed leaf by leaf."""
    normalized = normalize_factor_leaves(ConditionNode.model_validate({
        "field": "precision.grades",
        "op": "contains_any",
        "value": ["孔精加工", "珩孔要求"],
    }))

    assert normalized.any_conditions is not None
    assert [child.value for child in normalized.any_conditions] == ["孔精加工", "珩孔要求"]
    assert [child.op for child in normalized.any_conditions] == ["contains", "contains"]


def test_condition_value_lists_and_ranges_remain_one_factor_leaf():
    """Fails if material selections or numeric ranges are incorrectly decomposed."""
    material = ConditionNode(field="material.grade", op="in", value=["9Cr18", "95Cr18"])
    range_condition = ConditionNode(field="mechanical.hardness_hrc", op="between", value=[55, 60])

    assert normalize_factor_leaves(material).model_dump(mode="json") == material.model_dump(mode="json")
    assert normalize_factor_leaves(range_condition).model_dump(mode="json") == range_condition.model_dump(mode="json")


def test_exact_value_binds_but_unknown_value_does_not_guess():
    """Fails if a catalog binding is inferred from a merely similar value."""
    bound, issues = bind_unambiguous_factor_ids(ConditionNode(
        field="precision.grades", op="contains", value="孔精加工",
    ))
    assert bound.factor_id == "precision.hole_finish"
    assert issues == []

    unknown, issues = bind_unambiguous_factor_ids(ConditionNode(
        field="precision.grades", op="contains", value="自定义超精加工",
    ))
    assert unknown.factor_id is None
    assert [issue.code for issue in issues] == ["factor_unbound"]


def test_ambiguous_factor_match_retains_all_candidates():
    """Fails if ambiguity is silently assigned to the first matching factor."""
    node = ConditionNode(field="cad.features", op="contains", value="槽类特征")
    catalog = [
        StandardFactorDefinition(
            factor_id=f"test.slot.{index}", label="槽", category="结构特征",
            source_field="cad.features", canonical_value="槽类特征",
            allowed_operators=["contains"], kmai_factor_key=f"test_slot_{index}",
            kmai_value_mode="presence",
        )
        for index in (1, 2)
    ]

    matches = matching_standard_factors(node, _catalog=catalog)
    assert [factor.factor_id for factor in matches] == ["test.slot.1", "test.slot.2"]

    bound, issues = standard_factor_module._bind_leaf(node, "root", _catalog=catalog)
    assert bound.factor_id is None
    assert [(issue.code, issue.candidate_factor_ids) for issue in issues] == [
        ("factor_ambiguous", ["test.slot.1", "test.slot.2"]),
    ]


def test_every_compound_leaf_is_validated_independently():
    """Fails if a valid sibling hides an unbound condition in the same tree."""
    node = ConditionNode.model_validate({"all": [
        {
            "field": "cad.features", "op": "contains", "value": "顶尖孔",
            "factor_id": "feature.center_hole_location",
        },
        {"field": "precision.grades", "op": "contains", "value": "自定义值"},
    ]})

    assert [issue.path for issue in validate_factor_bindings(node)] == ["all[1]"]


def test_manual_process_boolean_has_no_standard_factor_binding():
    """Fails if a project-specific manual Boolean is given a standard factor identity."""
    node = ConditionNode(
        field="project_factor.manual_process_nitriding", op="eq", value=True,
    )

    bound, issues = bind_unambiguous_factor_ids(node)
    assert bound.factor_id is None
    assert issues == []
    assert validate_factor_bindings(bound) == []
