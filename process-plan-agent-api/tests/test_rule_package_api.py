from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _compile_payload(package_payload):
    return {
        "project_id": package_payload["manifest"]["project_id"],
        "package_name": package_payload["manifest"]["package_name"],
        "route_version_id": package_payload["manifest"]["route_version_id"],
        "applicability": package_payload["manifest"]["applicability"],
        "fields": package_payload["input_schema"]["fields"],
        "processes": package_payload["route_catalog"]["processes"],
        "rules": package_payload["route_rules"]["rules"],
        "test_cases": package_payload["test_cases"],
    }


def test_compile_validate_and_simulate_endpoints(rule_package_v2_payload):
    compiled = client.post(
        "/api/extract/finalized-rule-packages/compile",
        json=_compile_payload(rule_package_v2_payload),
    )
    assert compiled.status_code == 200
    compiled_body = compiled.json()
    assert compiled_body["validation"]["valid"] is True
    assert compiled_body["package"]["manifest"]["schema_version"] == "2.0"
    assert len(compiled_body["content_hash"]) == 64

    validated = client.post(
        "/api/extract/finalized-rule-packages/validate",
        json=compiled_body["package"],
    )
    assert validated.status_code == 200
    assert validated.json()["test_results"][0]["passed"] is True

    simulated = client.post(
        "/api/extract/finalized-rule-packages/simulate",
        json={
            "package": compiled_body["package"],
            "inputs": {
                "material": {"grade": "9Cr18"},
                "cad": {"features": ["槽类特征"]},
                "target_hardness_hrc": 58,
            },
        },
    )
    assert simulated.status_code == 200
    assert simulated.json()["plan"]["selected_process_ids"] == [
        "process_prepare",
        "process_rough_machine",
        "process_mill_slot",
        "process_quench",
    ]


def test_contract_rejects_unknown_condition_operator(rule_package_v2_payload):
    rule_package_v2_payload["route_rules"]["rules"][0]["when"] = {
        "field": "material.grade",
        "op": "regex",
        "value": ".*",
    }

    response = client.post(
        "/api/extract/finalized-rule-packages/validate",
        json=rule_package_v2_payload,
    )

    assert response.status_code == 422


def test_simulate_rejects_missing_required_input(rule_package_v2_payload):
    response = client.post(
        "/api/extract/finalized-rule-packages/simulate",
        json={
            "package": rule_package_v2_payload,
            "inputs": {"material": {"grade": "9Cr18"}},
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["code"] == "required_input_missing"


def test_simulate_rejects_non_string_multi_select_item(rule_package_v2_payload):
    response = client.post(
        "/api/extract/finalized-rule-packages/simulate",
        json={
            "package": rule_package_v2_payload,
            "inputs": {
                "material": {"grade": "9Cr18"},
                "cad": {"features": [123]},
            },
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["code"] == "input_type_mismatch"
