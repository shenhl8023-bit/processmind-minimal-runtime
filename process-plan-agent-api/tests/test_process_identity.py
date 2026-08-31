from app.services.rule_packages.process_identity import route_process_identities


def test_route_process_identity_prefers_persisted_export_id():
    identities = route_process_identities([
        {"id": "segment-heat", "normalized_step_name": "淬火", "export_process_id": "process_heat_treatment"},
        {"id": "segment-mark", "normalized_step_name": "标记"},
    ])

    assert [item.export_process_id for item in identities] == [
        "process_heat_treatment",
        "segment-mark",
    ]
