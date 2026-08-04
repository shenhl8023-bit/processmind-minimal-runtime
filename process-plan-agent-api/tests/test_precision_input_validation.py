import pytest

from app.services.rule_packages.condition_registry import input_field_for
from app.services.rule_packages.contracts import InputField, InputSchemaV2
from app.services.rule_packages.input_validation import validate_inputs


PRECISION_IT_FIELDS = [
    "precision.inner_diameter_it",
    "precision.dimension_it",
    "precision.outer_diameter_it",
]


def _schema(field_key: str) -> InputSchemaV2:
    field = input_field_for(field_key)
    assert field is not None
    return InputSchemaV2(fields=[field])


def _inputs(field_key: str, value: float) -> dict:
    return {"precision": {field_key.rsplit(".", 1)[-1]: value}}


@pytest.mark.parametrize("field_key", PRECISION_IT_FIELDS)
def test_precision_it_fields_declare_integer_range_5_to_10(field_key: str):
    field = input_field_for(field_key)

    assert field is not None
    assert field.validation is not None
    assert field.validation.min == 5
    assert field.validation.max == 10
    assert field.validation.integer is True


@pytest.mark.parametrize("field_key", PRECISION_IT_FIELDS)
def test_existing_package_precision_it_fields_are_normalized_to_current_range(field_key: str):
    field = InputField(
        key=field_key,
        label="legacy IT precision",
        type="number",
        validation={"min": 1, "max": 18},
    )

    assert field.validation is not None
    assert field.validation.min == 5
    assert field.validation.max == 10
    assert field.validation.integer is True


@pytest.mark.parametrize("field_key", PRECISION_IT_FIELDS)
@pytest.mark.parametrize("value", [5, 10])
def test_precision_it_fields_accept_integer_boundary_values(field_key: str, value: int):
    assert validate_inputs(_schema(field_key), _inputs(field_key, value)) == []


@pytest.mark.parametrize("field_key", PRECISION_IT_FIELDS)
@pytest.mark.parametrize(
    ("value", "error_code"),
    [(4, "input_below_min"), (11, "input_above_max"), (5.5, "input_integer_required")],
)
def test_precision_it_fields_reject_values_outside_integer_range(
    field_key: str,
    value: float,
    error_code: str,
):
    errors = validate_inputs(_schema(field_key), _inputs(field_key, value))

    assert [error.code for error in errors] == [error_code]
