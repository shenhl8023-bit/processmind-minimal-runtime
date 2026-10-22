from app.services.knowledge.local_search import search_local_knowledge


def test_historical_route_is_complete_and_numerically_ordered_even_with_top_k_one():
    result = search_local_knowledge("计量活门衬套1的工艺路线是什么？", top_k=1)

    assert result["intent"] == "history_route"
    assert len(result["items"]) == 1
    item = result["items"][0]
    route = item["route"]
    assert route["part_id"] == "J/RT145-13-02"
    assert route["operation_count"] == 27
    assert [operation["number"] for operation in route["operations"]] == [
        "0", "5", "10", "15", "20", "25", "30", "35", "40", "45", "50", "55", "60", "65",
        "70", "75", "80", "85", "90", "95", "100", "105", "110", "115", "120", "125", "130",
    ]
    assert [operation["name"] for operation in route["operations"][:6]] == [
        "下料", "调质", "车外形", "车外形", "铣扁", "钻铰孔",
    ]
    assert route["operations"][-1]["name"] == "包装"
    assert all(operation["source"]["document_name"] == "JRT145-13-02.json" for operation in route["operations"])
    assert route["operations"][0]["source"]["identity"] == "J/RT145-13-02:工序0"
    assert "0 下料 → 5 调质 → 10 车外形 → 15 车外形" in item["content"]
    assert "130 包装" in item["content"]


def test_historical_route_selection_expands_matching_operation_to_its_whole_case():
    result = search_local_knowledge("9Cr18 衬套含研孔的历史工艺路线有哪些？", top_k=2)

    assert len(result["items"]) == 2
    assert {item["route"]["part_id"] for item in result["items"]} == {"J/RT145-13-02", "J/RT145-15-01"}
    for item in result["items"]:
        assert item["route"]["material"] == "9Cr18"
        assert item["route"]["operation_count"] == 27
        assert item["route"]["operations"][0]["number"] == "0"
        assert item["route"]["operations"][-1]["number"] == "130"


def test_historical_route_keeps_part_identifier_and_material_constraints():
    result = search_local_knowledge("J/RT145-15-01 的完整历史工艺路线", top_k=8)

    assert len(result["items"]) == 1
    assert result["items"][0]["route"]["part_name"] == "计量活门衬套2"
    assert result["items"][0]["route"]["version"] == "A01"
    aluminum = search_local_knowledge("6061 衬套的历史工艺路线有哪些？")
    assert aluminum["items"]
    assert all(item["route"]["material"] == "6061" for item in aluminum["items"])
    assert search_local_knowledge("XQ-999 衬套的历史工艺路线有哪些？")["items"] == []


def test_historical_route_does_not_merge_process_versions(monkeypatch):
    records = []
    for version, numbers in (("A", (0, 5, 10)), ("B", (0, 8, 10))):
        for number in numbers:
            records.append({
                "id": f"part1-{version}-{number}", "category": "history", "title": "测试衬套",
                "fields": {"零件编号": "PART1", "零件名称": "测试衬套", "材料": "9Cr18",
                           "工艺规程编号": "P1", "版本": version, "工序号": str(number), "工序名称": f"工序{number}"},
                "source": {"document_name": "case.json", "identity": f"{version}:工序{number}"},
            })
    monkeypatch.setattr("app.services.knowledge.local_search._load_records", lambda: tuple(records))
    result = search_local_knowledge("测试衬套的历史工艺路线有哪些？")

    assert len(result["items"]) == 2
    assert len({item["id"] for item in result["items"]}) == 2
    assert {item["route"]["version"]: [op["number"] for op in item["route"]["operations"]] for item in result["items"]} == {
        "A": ["0", "5", "10"], "B": ["0", "8", "10"],
    }


def test_generic_feature_route_does_not_become_a_historical_part_route():
    result = search_local_knowledge("内孔粗加工路线有哪些？")

    assert result["intent"] == "capability"
    assert result["items"]
    assert all(item.get("route") is None for item in result["items"])

    methods = search_local_knowledge("查询钻孔、铰孔的加工路线")
    assert methods["intent"] == "capability"
    assert all(item["category"] == "capability" for item in methods["items"])


def test_route_query_does_not_substitute_other_parts_for_an_unknown_named_part():
    result = search_local_knowledge("火箭轴套的工艺路线是什么？")
    assert result["items"] == []


def test_route_resource_query_uses_actual_resources_from_the_selected_case():
    result = search_local_knowledge("计量活门衬套1的完整工艺路线和设备有哪些？", top_k=1)
    assert result["intent"] == "history_route"
    assert len(result["items"]) == 1
    route = result["items"][0]["route"]
    assert route["part_id"] == "J/RT145-13-02"
    assert route["operation_count"] == 27
    assert "QUEST 8/51" in result["items"][0]["content"]
    assert any(op.get("equipment") for op in route["operations"])


def test_route_operation_filter_selects_whole_matching_cases_only():
    result = search_local_knowledge("9Cr18 衬套含研孔的历史工艺路线有哪些？", top_k=50)
    assert result["items"]
    assert all(any(op["name"] == "研孔" for op in item["route"]["operations"]) for item in result["items"])
    assert search_local_knowledge("6061 衬套含真空淬火的历史工艺路线有哪些？")["items"] == []


def test_route_does_not_substitute_another_version_or_claim_a_whole_route_target():
    assert search_local_knowledge("计量活门衬套1的B版本工艺路线")["items"] == []
    result = search_local_knowledge("9Cr18 衬套的历史工艺路线有哪些，Ra1.6？")
    assert result["status"] == "insufficient_evidence"


def test_complete_operation_route_wording_uses_full_case():
    result = search_local_knowledge("计量活门衬套1的完整工序路线")
    assert result["items"][0]["route"]["operation_count"] == 27


def test_route_operation_exclusions_are_not_interpreted_as_requirements():
    result = search_local_knowledge("9Cr18 衬套不含研孔的历史工艺路线有哪些？")
    assert len(result["items"]) == 2
    assert all(not any(op["name"] == "研孔" for op in item["route"]["operations"]) for item in result["items"])
    assert len(search_local_knowledge("6061 衬套不含真空淬火的历史工艺路线有哪些？")["items"]) == 2


def test_route_unknown_part_number_suffix_does_not_match_a_shorter_part_name():
    assert search_local_knowledge("计量活门衬套3的工艺路线是什么？")["items"] == []


def test_local_search_returns_traceable_axle_sleeve_process_evidence():
    result = search_local_knowledge("9Cr18 车外圆", top_k=8)

    assert result["status"] == "ok"
    assert result["items"]
    assert "历史" in result["answer"]
    history = next(item for item in result["items"] if item["category"] == "history")
    assert "9Cr18" in history["content"]
    assert history["source"]["document_name"].endswith(".json")
    assert "工序" in history["source"]["identity"]


def test_local_search_explains_when_no_local_evidence_matches():
    result = search_local_knowledge("完全不存在的材料XQ-999", top_k=8)

    assert result["status"] == "ok"
    assert result["items"] == []
    assert "没有找到" in result["message"]
    assert result["answer"] == ""


def test_local_search_covers_equipment_tool_gauge_and_capability_records():
    cases = {
        "equipment": "CL6134A",
        "tool": "标准高速钢麻花钻",
        "gauge": "外径千分尺",
        "capability": "精镗床加工精度",
    }

    for category, query in cases.items():
        result = search_local_knowledge(query, top_k=8)

        assert result["items"], query
        assert any(item["category"] == category for item in result["items"]), query
        assert all(item["source"]["document_name"] for item in result["items"])


def test_resource_catalog_query_returns_only_requested_entity_records():
    result = search_local_knowledge("设备有哪些？", top_k=20)

    assert result["intent"] == "equipment"
    assert result["items"]
    assert all(item["category"] == "equipment" for item in result["items"])
    assert any("CL6134A" in item["content"] for item in result["items"])


def test_equipment_catalog_accepts_natural_language_count_questions():
    for query in ("有没有设备？", "所有设备", "设备不是有很多嘛"):
        result = search_local_knowledge(query, top_k=8)

        assert result["intent"] == "equipment"
        assert result["resource_summary"]["record_count"] >= 300
        assert all(item["category"] == "equipment" for item in result["items"])


def test_historical_sleeve_resource_query_exposes_deduplicated_summary():
    result = search_local_knowledge("某历史轴套类工序使用了哪些设备和量具？", top_k=5)

    summary = result["resource_summary"]
    assert summary["record_count"] >= len(result["items"])
    assert summary["equipment_count"] > len(result["items"])
    assert summary["equipment"]
    assert all(item["name"] for item in summary["equipment"])
    assert any(item.get("model") for item in summary["equipment"])
    assert all(item["sources"] for item in summary["equipment"])


def test_capability_search_matches_precision_and_roughness_targets_as_ranges():
    result = search_local_knowledge("内孔目标 IT7、Ra1.6，样例库有哪些工艺方法？", top_k=20)

    capabilities = [item for item in result["items"] if item["category"] == "capability"]
    assert capabilities
    assert all(item["capability"]["precision"]["min_grade"] <= 7 <= item["capability"]["precision"]["max_grade"] for item in capabilities)
    assert all(item["capability"]["roughness"]["min_um"] <= 1.6 <= item["capability"]["roughness"]["max_um"] for item in capabilities)
    assert all(item["capability"]["feature"] in {"孔", "内孔", None} for item in capabilities)


def test_capability_search_prioritizes_explicit_method_and_equipment_category():
    result = search_local_knowledge("卧式铣镗床粗镗的精度和粗糙度是多少？", top_k=8)

    capabilities = [item for item in result["items"] if item["category"] == "capability"]
    assert capabilities
    assert capabilities[0]["id"] == "CP-014"
    assert all(item["capability"]["method"] == "粗镗" for item in capabilities)


def test_capability_items_expose_metric_groups_and_evidence_based_relationship_status():
    linked_tool = search_local_knowledge("CP-010", top_k=1)["items"][0]
    linked_equipment = search_local_knowledge("CP-014", top_k=1)["items"][0]
    unlinked_gauge = search_local_knowledge("CP-005", top_k=1)["items"][0]

    assert linked_tool["capability"]["method"] == "铰孔"
    assert linked_tool["capability"]["precision"]["type"] == "经济精度等级"
    assert linked_tool["relationships"]["tool"]["status"] == "linked"
    assert linked_tool["relationships"]["tool"]["items"][0]["id"] == "TL-003"
    assert linked_equipment["relationships"]["equipment"]["status"] == "linked"
    assert linked_equipment["relationships"]["equipment"]["items"][0]["id"] == "EQ-006"
    assert unlinked_gauge["relationships"]["gauge"]["status"] == "not_provided"


def test_equipment_category_question_reports_missing_capability_relationships_without_guessing():
    result = search_local_knowledge("加工外圆时，哪些车床类别有对应的能力记录？", top_k=20)

    assert result["intent"] == "capability"
    assert result["status"] == "insufficient_evidence"
    assert result["relationship_gaps"] == ["equipment"]
    assert result["answer"] == ""
    assert result["items"]
    assert all(item["relationships"]["equipment"]["status"] == "not_provided" for item in result["items"] if item["category"] == "capability")


def test_vague_capability_relationship_question_does_not_turn_unrelated_history_into_an_answer():
    result = search_local_knowledge("某能力适用哪些量具？", top_k=20)

    assert result["status"] == "insufficient_evidence"
    assert result["relationship_gaps"] == ["gauge"]
    assert result["answer"] == ""


def test_historical_sleeve_equipment_and_gauge_query_prioritizes_processes_with_both():
    result = search_local_knowledge("某历史轴套类工序使用了哪些设备和量具？", top_k=5)

    history = [item for item in result["items"] if item["category"] == "history"]
    assert history
    assert any("设备：[" in item["content"] for item in history)
    assert any("量具：[" in item["content"] for item in history)
    assert any("设备：[]" not in item["content"] and "量具：[]" not in item["content"] for item in history)
    assert all(any(marker in item["content"] for marker in ("轴套", "衬套", "套筒")) for item in history)


def test_gauge_catalog_filters_by_inner_diameter_and_full_requested_range():
    result = search_local_knowledge("内径 20～25 mm 的孔，可以查到哪些量具？", top_k=20)

    assert result["intent"] == "gauge"
    assert result["resource_summary"]["record_count"] == 3
    assert result["resource_summary"]["gauge_count"] == 3
    assert {item["id"] for item in result["items"]} == {"gauge-84", "gauge-174", "gauge-182"}
    assert all(item["category"] == "gauge" for item in result["items"])
    assert all("测量对象：内径" in item["content"] for item in result["items"])


def test_capability_search_recognizes_processing_stage_and_feature():
    result = search_local_knowledge("轴套内孔粗加工有哪些方法？", top_k=20)

    assert result["intent"] == "capability"
    capabilities = [item for item in result["items"] if item["category"] == "capability"]
    assert capabilities
    assert all(item["capability"]["stage"] == "粗加工阶段" for item in capabilities)
    assert all(item["capability"]["feature"] in {"孔", "内孔"} for item in capabilities)


def test_history_catalog_query_returns_historical_cases():
    result = search_local_knowledge("有哪些历史案例？", top_k=8)

    assert result["intent"] == "history"
    assert result["items"]
    assert all(item["category"] == "history" for item in result["items"])
    assert result["resource_summary"]["scope"] == "catalog"
    assert result["resource_summary"]["record_count"] >= len(result["items"])


def test_exact_precision_method_query_excludes_plain_reaming_rows():
    result = search_local_knowledge("精铰孔能达到什么精度和 Ra？", top_k=20)

    capabilities = [item for item in result["items"] if item["category"] == "capability"]
    assert capabilities
    assert all(item["capability"]["method"] == "精铰" for item in capabilities)


def test_specific_device_capability_without_device_identifier_is_insufficient():
    result = search_local_knowledge("某具体设备能达到什么精度？", top_k=20)

    assert result["intent"] == "capability"
    assert result["status"] == "insufficient_evidence"
    assert result["relationship_gaps"] == ["equipment"]
    assert result["answer"] == ""


def test_device_model_precision_uses_its_own_parameters_instead_of_generic_capabilities():
    result = search_local_knowledge("CL6134A 能达到什么精度？")

    assert result["status"] == "ok"
    assert result["intent"] == "equipment"
    assert result["items"]
    assert all(item["category"] == "equipment" and "CL6134A" in item["content"] for item in result["items"])


def test_unknown_or_unlinked_device_model_never_matches_generic_capability():
    for query in ("XQ999设备能达到什么精度？", "CL6134A 粗镗能达到什么精度？"):
        result = search_local_knowledge(query)

        assert result["items"] == [], query
        assert result["answer"] == "", query


def test_named_equipment_category_capability_is_not_blocked_or_mixed_with_other_equipment():
    result = search_local_knowledge("卧式铣镗床粗镗的精度和粗糙度是多少？")

    assert result["status"] == "ok"
    assert result["relationship_gaps"] == []
    assert result["items"][0]["id"] == "CP-014"
    for item in result["items"]:
        assert any("卧式铣镗床" in relation["name"] for relation in item["relationships"]["equipment"]["items"])


def test_longer_method_names_do_not_include_embedded_shorter_methods():
    result = search_local_knowledge("半精镗能达到什么精度？", top_k=20)

    assert result["items"]
    assert all(item["capability"]["method"] == "半精镗" for item in result["items"])


def test_multiple_processing_stages_and_features_are_preserved():
    result = search_local_knowledge("内孔粗加工和精加工有哪些能力？", top_k=20)

    assert result["items"]
    assert {item["capability"]["stage"] for item in result["items"]} >= {"粗加工阶段", "精加工阶段"}
    assert all(item["capability"]["feature"] in {"孔", "内孔"} for item in result["items"])
    result = search_local_knowledge("轴套内孔和外圆有哪些加工方法？", top_k=8)
    assert any(item["capability"]["feature"] in {"孔", "内孔"} for item in result["items"])
    assert any("外圆" in str(item["capability"]["feature"]) for item in result["items"])


def test_catalog_summary_keeps_parameter_variants_and_complete_structured_sources():
    result = search_local_knowledge("设备有哪些？")
    summary = result["resource_summary"]

    assert summary["record_count"] == 370
    assert summary["unique_count"] == 290
    assert all(entry.get("fields") for entry in summary["equipment"])
    assert all(isinstance(source, dict) and source.get("worksheet") and source.get("row_no") and source.get("cell_range") for entry in summary["equipment"] for source in entry["sources"])


def test_comparison_query_retains_each_requested_method_in_visible_evidence():
    result = search_local_knowledge("钻孔、扩孔、铰孔分别适合什么加工阶段和精度范围？", top_k=3)

    assert {item["capability"]["method"] for item in result["items"]} == {"钻孔", "扩孔", "铰孔"}


def test_material_constraints_are_not_silently_dropped():
    assert search_local_knowledge("9Cr18 轴套内孔粗加工有哪些方法？")["items"] == []
    result = search_local_knowledge("铸铁内孔粗镗能达到什么精度？", top_k=20)
    assert result["items"]
    assert all(item["capability"]["material"] == "铸铁" for item in result["items"])
    assert search_local_knowledge("钛合金内孔精镗能达到什么精度？")["items"] == []


def test_capability_relationship_gaps_use_the_evidence_actually_returned():
    result = search_local_knowledge("内孔加工能力有哪些设备和刀具？", top_k=8)
    assert result["status"] == "ok"
    for relation in ("equipment", "tool"):
        assert any(item["relationships"][relation]["status"] in {"linked", "category_hint"} for item in result["items"])
    result = search_local_knowledge("内孔加工能力有哪些设备和刀具？", top_k=1)
    for relation in ("equipment", "tool"):
        has_evidence = any(item["relationships"][relation]["status"] in {"linked", "category_hint"} for item in result["items"])
        assert has_evidence or relation in result["relationship_gaps"]


def test_equipment_subtype_catalog_does_not_return_other_machine_categories():
    result = search_local_knowledge("有哪些车床设备？", top_k=20)
    assert result["items"]
    assert all("设备类别：车床" in item["content"] for item in result["items"])


def test_reversed_source_ranges_are_flagged_without_inventing_corrected_values():
    item = search_local_knowledge("CP-636", top_k=1)["items"][0]
    assert item["data_warnings"]
    assert "不作为适配或能力结论依据" in item["content"]
    assert item["capability"]["roughness"]["bounds_valid"] is False
    assert item["capability"]["roughness"]["min_um"] is None
    assert item["capability"]["roughness"]["max_um"] is None
    result = search_local_knowledge("量具有哪些？", top_k=50)
    assert any(entry.get("data_warnings") for entry in result["resource_summary"]["gauge"])


def test_precision_targets_work_without_whitespace_at_chinese_boundaries():
    result = search_local_knowledge("内孔目标IT7级、Ra1.6微米有哪些加工方法？", top_k=20)
    assert result["items"]
    assert all(item["capability"]["precision"]["min_grade"] <= 7 <= item["capability"]["precision"]["max_grade"] for item in result["items"])
    assert all(item["capability"]["roughness"]["min_um"] <= 1.6 <= item["capability"]["roughness"]["max_um"] for item in result["items"])


def test_gauge_record_id_is_not_mistaken_for_a_measurement_dimension():
    result = search_local_knowledge("GA-110量具参数是什么？", top_k=8)
    assert result["items"]
    assert all("量具ID：GA-110" in item["content"] for item in result["items"])


def test_equipment_precision_parameter_catalog_is_not_treated_as_missing_capability_link():
    result = search_local_knowledge("CL6134A 车床的加工范围和精度参数是什么？")
    assert result["status"] == "ok"
    assert result["intent"] == "equipment"
    assert result["relationship_gaps"] == []
    assert result["items"]


def test_capability_id_relationship_queries_report_missing_links():
    result = search_local_knowledge("CP-014适用哪些量具？")
    assert result["intent"] == "capability"
    assert result["status"] == "insufficient_evidence"
    assert result["relationship_gaps"] == ["gauge"]
    assert [item["id"] for item in result["items"]] == ["CP-014"]


def test_named_tool_precision_only_uses_explicit_matching_relationships():
    result = search_local_knowledge("镗刀能达到什么经济精度？", top_k=20)
    assert result["status"] == "ok"
    assert result["intent"] == "capability"
    assert any(item["id"] == "CP-011" for item in result["items"])
    assert all(
        any("镗刀" in related["name"] for related in item["relationships"]["tool"]["items"])
        for item in result["items"]
    )


def test_specific_tool_without_precision_relationship_is_insufficient():
    result = search_local_knowledge("标准高速钢麻花钻能达到什么经济精度？")
    assert result["status"] == "insufficient_evidence"
    assert result["relationship_gaps"] == ["tool"]
    assert result["answer"] == ""


def test_named_tool_applicable_method_uses_direct_master_data():
    result = search_local_knowledge("铰刀适用于哪些加工方法？")
    assert result["status"] == "ok"
    assert result["intent"] == "tool"
    assert result["items"]
    assert all(item["category"] == "tool" and "适用加工方法：铰孔" in item["content"] for item in result["items"])


def test_tool_id_precision_uses_linked_capability_instead_of_parameter_catalog():
    result = search_local_knowledge("TL-004能达到什么经济精度？")
    assert result["status"] == "ok"
    assert result["intent"] == "capability"
    assert [item["id"] for item in result["items"]] == ["CP-011"]


def test_named_tool_precision_parameter_wording_still_requires_capability_evidence():
    result = search_local_knowledge("镗刀精度参数是什么？")
    assert result["intent"] == "capability"
    assert result["status"] == "ok"
    assert result["items"]
    assert all(item["category"] == "capability" for item in result["items"])
    assert any(item["id"] == "CP-011" for item in result["items"])


def test_entity_ids_without_machining_precision_do_not_return_parameter_catalog():
    for query in ("TL-007能达到什么经济精度？", "GA-110量具能达到什么经济精度？"):
        result = search_local_knowledge(query)
        assert result["items"] == [] or result["status"] == "insufficient_evidence"
        assert result["answer"] == ""


def test_history_tool_queries_do_not_use_gauge_or_generic_operation_records():
    named = search_local_knowledge("历史轴套使用哪些铰刀？")
    assert named["items"] == [] or named["status"] == "insufficient_evidence"
    generic = search_local_knowledge("历史轴套工序用了哪些刀具？")
    assert generic["status"] == "insufficient_evidence"
    assert generic["relationship_gaps"] == ["tool"]
    assert generic["answer"] == ""
