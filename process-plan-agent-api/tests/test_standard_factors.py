from app.services.rule_packages.contracts import ConditionNode
from app.services.rule_packages.standard_factors import bind_unambiguous_factor_ids


def test_binds_clear_hole_aliases_to_canonical_standard_factors():
    source = ConditionNode(
        any=[
            ConditionNode(field="cad.features", op="contains", value="内孔"),
            ConditionNode(field="cad.features", op="contains", value="通孔"),
            ConditionNode(field="cad.features", op="contains", value="中心孔"),
        ]
    )

    bound, issues = bind_unambiguous_factor_ids(source)

    assert issues == []
    assert bound.any_conditions is not None
    assert [child.value for child in bound.any_conditions] == ["普通孔/辅助孔", "顶尖孔"]
    assert [child.factor_id for child in bound.any_conditions] == [
        "feature.standard_or_aux_hole",
        "feature.center_hole_location",
    ]


def test_splits_enumerated_hole_aliases_before_binding():
    source = ConditionNode(
        field="cad.features",
        op="contains",
        value="内孔、通孔或中心孔",
    )

    bound, issues = bind_unambiguous_factor_ids(source)

    assert issues == []
    assert bound.any_conditions is not None
    assert [child.value for child in bound.any_conditions] == ["普通孔/辅助孔", "顶尖孔"]


def test_keeps_unknown_mixed_feature_value_unbound_instead_of_dropping_it():
    source = ConditionNode(
        field="cad.features",
        op="contains",
        value="内孔或未知异形结构",
    )

    bound, issues = bind_unambiguous_factor_ids(source)

    assert bound.field == "cad.features"
    assert bound.value == "内孔或未知异形结构"
    assert bound.factor_id is None
    assert [issue.code for issue in issues] == ["factor_unbound"]


def test_binds_explicit_shaped_hole_alias_without_using_the_process_name():
    source = ConditionNode(field="cad.features", op="contains", value="异形孔")

    bound, issues = bind_unambiguous_factor_ids(source)

    assert issues == []
    assert bound.value == "型孔/割扁"
    assert bound.factor_id == "feature.shaped_hole_or_cut_flat"
