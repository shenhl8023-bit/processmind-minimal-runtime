from app.services.rule_packages.kmai_export import build_kmai_compatibility_export
from app.services.rule_packages.kmai_export_context import FactorRegistry
from app.services.rule_packages.kmai_export_factors import (
    build_factor_expansion_rules,
    build_factor_schema,
    dynamic_factor,
)


def test_factor_schema_appends_registered_dynamic_factors_in_registration_order(
    rule_package_v2,
):
    registry = FactorRegistry()
    first = {"factor_key": "dynamic_first", "factor_id": "F900"}
    second = {"factor_key": "dynamic_second", "factor_id": "F901"}
    registry.register("dynamic_first", first)
    registry.register("dynamic_second", second)

    schema = build_factor_schema(rule_package_v2, registry)

    assert schema["factors"][-2:] == [first, second]


def test_dynamic_factor_allocates_stable_consecutive_ids(rule_package_v2):
    registry = FactorRegistry()

    first_key = dynamic_factor(rule_package_v2, "mechanical.hardness_hrc", registry)
    second_key = dynamic_factor(rule_package_v2, "custom.secondary", registry)

    assert dynamic_factor(rule_package_v2, "mechanical.hardness_hrc", registry) == first_key
    assert [(item["factor_key"], item["factor_id"]) for item in registry.values()] == [
        (first_key, "F900"),
        (second_key, "F901"),
    ]


def test_factor_builders_match_the_facade_artifacts_for_existing_fixture(rule_package_v2):
    registry = FactorRegistry()
    assert dynamic_factor(rule_package_v2, "mechanical.hardness_hrc", registry) == (
        "mechanical_hardness_hrc"
    )

    assert build_factor_schema(rule_package_v2, registry) == build_kmai_compatibility_export(
        rule_package_v2
    ).files["factor_schema.json"]
    assert build_factor_expansion_rules(rule_package_v2) == build_kmai_compatibility_export(
        rule_package_v2
    ).files["factor_expansion_rules.json"]
