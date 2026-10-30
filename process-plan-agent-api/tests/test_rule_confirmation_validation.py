import hashlib
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.models.models import NormalizedRouteSegmentRuleReview, NormalizedRouteVersion, Project
from app.services.rule_packages.condition_contracts import RuleConditionCandidate
from app.services.rule_packages.confirmation_validation import require_confirmed_user_rule_sources
from app.services.rule_packages.contracts import RulePackageV2


SOURCE_TEXT = "当材料牌号为 9Cr18 时，纳入淬火工序。"
CONFIRMED_AT = datetime(2026, 10, 27, 6, 0, tzinfo=timezone.utc)
SEGMENT_ID = "quench_segment"


def condition_candidate():
    return RuleConditionCandidate.model_validate({
        "when": {"field": "material.grade", "op": "eq", "value": "9Cr18"},
        "then": {"include_process_ids": ["process_quench"], "exclude_process_ids": []},
    })


def relation_candidate():
    return RuleConditionCandidate.model_validate({
        "kind": "process_relation",
        "relation": {
            "relation_type": "trigger_after", "source_process_ids": ["process_prepare"],
            "target_process_ids": ["process_quench"], "source_match": "any",
        },
    })


def review_row(status="confirmed", candidate=None, source_text=SOURCE_TEXT, **updates):
    candidate = candidate or condition_candidate()
    values = {
        "project_id": 12, "route_version_id": 31, "segment_id": SEGMENT_ID,
        "condition_source_text": source_text,
        "condition_source_hash": hashlib.sha256(source_text.encode()).hexdigest(),
        "condition_status": status,
        "condition_candidate_json": candidate.model_dump_json(by_alias=True),
        "condition_confirmed_json": candidate.model_dump_json(by_alias=True) if status == "confirmed" else None,
        "condition_confirmed_by": "默认用户" if status == "confirmed" else None,
        "condition_confirmed_at": CONFIRMED_AT if status == "confirmed" else None,
    }
    values.update(updates)
    return NormalizedRouteSegmentRuleReview(**values)


@asynccontextmanager
async def review_session(tmp_path, rows, *, process_name="淬火"):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'confirmation.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as session:
            session.add(Project(id=12, name="发布来源验证", status="ROUTE_SET_READY"))
            session.add(NormalizedRouteVersion(
                id=31, project_id=12, version=1,
                route_json=json.dumps([{
                    "id": SEGMENT_ID, "export_process_id": "process_quench", "normalized_step_name": process_name,
                }], ensure_ascii=False),
            ))
            session.add_all(rows)
            await session.commit()
            yield session
    finally:
        await engine.dispose()


def package_with_confirmation(payload, candidate, *, source="user_confirmed", enabled=True):
    package = RulePackageV2.model_validate(payload)
    metadata = {
        "source": source, "enabled": enabled, "source_segment_id": SEGMENT_ID,
        "source_text": SOURCE_TEXT, "confirmed_by": "默认用户", "confirmed_at": CONFIRMED_AT.isoformat(),
    }
    if candidate.kind == "condition":
        from app.services.rule_packages.contracts import RuleV2

        package.route_rules.rules.append(RuleV2(
            rule_id="user.quench", when=candidate.when, then=candidate.then, **metadata,
        ))
    else:
        from app.services.rule_packages.contracts import ProcessRelationV2

        package.route_rules.process_relations.append(ProcessRelationV2(
            relation_id="relation.quench", **candidate.relation.model_dump(), **metadata,
        ))
    return package


async def require_sources(package, session):
    return await require_confirmed_user_rule_sources(
        package, project_id=12, route_version_id=31, db=session,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize('mutation', ['valid', 'omitted', 'changed', 'disabled', 'field_label'])
async def test_unified_configuration_publication_matches_full_confirmation(tmp_path, rule_package_v2_payload, mutation):
    from app.services.rule_packages.contracts import ProcessConfigurationV2
    config = {
        'process_id': 'process_quench', 'occurrence': 'conditional',
        'when': {'field': 'project_factor.category', 'op': 'eq', 'value': 'A'},
        'relations': [{'relation_type': 'trigger_after', 'source_process_ids': ['process_prepare'], 'target_process_ids': ['process_quench'], 'source_match': 'all'}],
    }
    field = {'key': 'project_factor.category', 'label': '类型', 'category': '项目', 'type': 'single_select', 'operators': ['eq'], 'options': [{'value': 'A', 'label': 'A'}], 'allow_custom': False}
    candidate = RuleConditionCandidate.model_validate({'kind': 'process_configuration', 'configuration': config, 'field_definitions': [field]})
    package = RulePackageV2.model_validate(rule_package_v2_payload)
    from app.services.rule_packages.contracts import InputField
    definition = InputField.model_validate({key: value for key, value in field.items() if key not in {'category', 'operators'}})
    package.input_schema.fields.append(definition)
    package.factor_dictionary.fields.append(definition.model_copy(deep=True))
    if mutation != 'omitted':
        package.route_rules.process_configurations.append(ProcessConfigurationV2(**config, source='user_confirmed', source_segment_id=SEGMENT_ID, source_text=SOURCE_TEXT, confirmed_by='默认用户', confirmed_at=CONFIRMED_AT.isoformat(), enabled=mutation != 'disabled'))
    if mutation == 'changed':
        package.route_rules.process_configurations[0].relations = []
    if mutation == 'field_label':
        package.input_schema.fields[-1].label = '伪造标签'
    async with review_session(tmp_path, [review_row(candidate=candidate)]) as session:
        if mutation == 'valid':
            await require_sources(package, session)
        else:
            with pytest.raises(HTTPException) as error:
                await require_sources(package, session)
            assert error.value.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize('mutation', ['valid', 'missing_option', 'extra_option', 'option_label', 'field_label', 'type', 'source', 'required', 'allow_custom', 'unit'])
async def test_shared_configuration_field_publishes_only_the_confirmed_option_union(tmp_path, rule_package_v2_payload, mutation):
    from app.services.rule_packages.contracts import InputField, ProcessConfigurationV2
    field = {'key': 'project_factor.treatment_class', 'label': '处理类别', 'category': '项目', 'type': 'single_select', 'operators': ['eq'], 'allow_custom': False, 'source': '用户直接设定'}
    package = RulePackageV2.model_validate(rule_package_v2_payload)
    rows = []
    for segment, process_id, value in [(SEGMENT_ID, 'process_quench', 'A'), ('finishing', 'process_mill_slot', 'B')]:
        config = {'process_id': process_id, 'occurrence': 'conditional', 'when': {'field': field['key'], 'op': 'eq', 'value': value}, 'relations': []}
        candidate = RuleConditionCandidate.model_validate({'kind': 'process_configuration', 'configuration': config, 'field_definitions': [{**field, 'options': [{'value': value, 'label': value}]}]})
        rows.append(review_row(candidate=candidate, segment_id=segment))
        package.route_rules.process_configurations.append(ProcessConfigurationV2(**config, source='user_confirmed', source_segment_id=segment, source_text=SOURCE_TEXT, confirmed_by='默认用户', confirmed_at=CONFIRMED_AT.isoformat()))
    definition = InputField.model_validate({key: value for key, value in field.items() if key in InputField.model_fields})
    from app.services.rule_packages.contracts import InputOption
    definition.options = [InputOption(value='A', label='A'), InputOption(value='B', label='B')]
    if mutation == 'missing_option':
        definition.options.pop()
    elif mutation == 'extra_option':
        definition.options.append(InputOption(value='C', label='C'))
    elif mutation == 'option_label':
        definition.options[-1].label = '伪造'
    elif mutation != 'valid':
        attribute = 'label' if mutation == 'field_label' else mutation
        setattr(definition, attribute, {'field_label': '伪造', 'type': 'multi_select', 'source': '伪造', 'required': True, 'allow_custom': True, 'unit': 'mm'}[mutation])
    package.input_schema.fields.append(definition)
    package.factor_dictionary.fields.append(definition.model_copy(deep=True))
    async with review_session(tmp_path, rows) as session:
        if mutation == 'valid':
            await require_sources(package, session)
        else:
            with pytest.raises(HTTPException) as error:
                await require_sources(package, session)
            assert error.value.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["draft", "parsing", "pending_confirmation", "invalid"])
async def test_unconfirmed_persisted_condition_cannot_be_hidden_as_mainline(
    tmp_path, rule_package_v2_payload, status,
):
    package = RulePackageV2.model_validate(rule_package_v2_payload)
    next(process for process in package.route_catalog.processes if process.process_id == "process_quench").main = True
    async with review_session(tmp_path, [review_row(status=status)]) as session:
        with pytest.raises(HTTPException) as error:
            await require_sources(package, session)
        assert error.value.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["condition", "relation"])
@pytest.mark.parametrize("export_mode", ["omitted", "system_static", "disabled"])
async def test_confirmed_source_must_be_included_and_enabled(
    tmp_path, rule_package_v2_payload, kind, export_mode,
):
    candidate = condition_candidate() if kind == "condition" else relation_candidate()
    package = RulePackageV2.model_validate(rule_package_v2_payload) if export_mode == "omitted" else package_with_confirmation(
        rule_package_v2_payload, candidate,
        source="system_static" if export_mode == "system_static" else "user_confirmed",
        enabled=export_mode != "disabled",
    )
    async with review_session(tmp_path, [review_row(candidate=candidate)]) as session:
        with pytest.raises(HTTPException) as error:
            await require_sources(package, session)
        assert error.value.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["condition", "relation"])
async def test_current_confirmed_source_can_be_published(tmp_path, rule_package_v2_payload, kind):
    candidate = condition_candidate() if kind == "condition" else relation_candidate()
    package = package_with_confirmation(rule_package_v2_payload, candidate)
    async with review_session(tmp_path, [review_row(candidate=candidate)]) as session:
        await require_sources(package, session)


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["valid", "field_label", "option_label", "extra_option", "dictionary_missing"])
async def test_legacy_confirmations_publish_only_the_confirmed_field_definitions(
    tmp_path, rule_package_v2_payload, mutation,
):
    from app.services.rule_packages.contracts import InputField, InputOption

    candidate = condition_candidate()
    definition = {
        "key": "project_factor.treatment_class", "label": "处理类别",
        "category": "项目", "type": "single_select", "operators": ["eq"],
        "allow_custom": False, "options": [{"value": "A", "label": "处理A"}],
    }
    candidate = RuleConditionCandidate.model_validate({
        **candidate.model_dump(), "field_definitions": [definition],
    })
    candidate.when.field = definition["key"]
    candidate.when.value = "A"
    package = package_with_confirmation(rule_package_v2_payload, candidate)
    exported = InputField.model_validate({key: value for key, value in definition.items() if key in InputField.model_fields})
    package.input_schema.fields.append(exported)
    package.factor_dictionary.fields.append(exported.model_copy(deep=True))
    if mutation == "field_label":
        exported.label = "未经确认的标签"
    elif mutation == "option_label":
        exported.options[0].label = "未经确认的含义"
    elif mutation == "extra_option":
        exported.options.append(InputOption(value="B", label="处理B"))
    elif mutation == "dictionary_missing":
        package.factor_dictionary.fields.pop()
    async with review_session(tmp_path, [review_row(candidate=candidate)]) as session:
        if mutation == "valid":
            await require_sources(package, session)
        else:
            with pytest.raises(HTTPException) as error:
                await require_sources(package, session)
            assert error.value.status_code == 409
            assert error.value.detail["segment_ids"] == [SEGMENT_ID]


@pytest.mark.asyncio
async def test_unreviewed_legacy_sources_do_not_need_new_confirmations(tmp_path, rule_package_v2_payload):
    package = RulePackageV2.model_validate(rule_package_v2_payload)
    untouched = NormalizedRouteSegmentRuleReview(
        project_id=12, route_version_id=31, segment_id=SEGMENT_ID, decision="accepted",
    )
    async with review_session(tmp_path, [untouched]) as session:
        await require_sources(package, session)


@pytest.mark.asyncio
async def test_explicit_saved_mainline_conversion_can_be_published(tmp_path, rule_package_v2_payload):
    package = RulePackageV2.model_validate(rule_package_v2_payload)
    next(process for process in package.route_catalog.processes if process.process_id == "process_quench").main = True
    conversion = review_row(
        status="draft", source_text="设置为主工序，始终纳入“淬火”工序。",
        condition_candidate_json=None, condition_confirmed_json=None,
    )
    async with review_session(tmp_path, [conversion]) as session:
        await require_sources(package, session)


@pytest.mark.asyncio
async def test_mainline_conversion_must_be_reflected_in_the_catalog(tmp_path, rule_package_v2_payload):
    conversion = review_row(
        status="draft", source_text="设置为主工序，始终纳入“淬火”工序。",
        condition_candidate_json=None, condition_confirmed_json=None,
    )
    async with review_session(tmp_path, [conversion]) as session:
        with pytest.raises(HTTPException) as error:
            await require_sources(RulePackageV2.model_validate(rule_package_v2_payload), session)
        assert error.value.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize("source_text", [
    "不得设置为主工序，应当按材料牌号决定。",
    "设置为主工序，仅当材料牌号为9Cr18时纳入。",
    "设置为主工序，始终纳入“淬火”工序。仅在硬度达到 HRC55 时安排。",
    "将其设置为主工序，始终保留在路线中，但材料牌号为9Cr18时除外。",
    "设置为主工序，始终纳入“渗氮”工序。",
])
async def test_mainline_exemption_rejects_qualified_negated_or_wrong_process_instructions(
    tmp_path, rule_package_v2_payload, source_text,
):
    package = RulePackageV2.model_validate(rule_package_v2_payload)
    process = next(process for process in package.route_catalog.processes if process.process_id == "process_quench")
    process.main = True
    # The process identity is server-owned. Renaming the exported catalog to
    # match a wrong instruction must not make that instruction authoritative.
    process.display_name = "渗氮"
    conversion = review_row(
        status="draft", source_text=source_text,
        condition_candidate_json=None, condition_confirmed_json=None,
    )
    async with review_session(tmp_path, [conversion]) as session:
        with pytest.raises(HTTPException) as error:
            await require_sources(package, session)
        assert error.value.status_code == 409
        assert error.value.detail["segment_ids"] == [SEGMENT_ID]


@pytest.mark.asyncio
@pytest.mark.parametrize("source_text", [
    "将其设置为主工序，始终保留在路线中",
    "把该工序改为主线工序",
    "作为基础工序无条件进入路线",
    "此工序属于必经工序",
    "固定为主工序，默认保留",
])
async def test_exact_legacy_mainline_instructions_remain_publishable(
    tmp_path, rule_package_v2_payload, source_text,
):
    package = RulePackageV2.model_validate(rule_package_v2_payload)
    next(process for process in package.route_catalog.processes if process.process_id == "process_quench").main = True
    conversion = review_row(
        status="draft", source_text=source_text,
        condition_candidate_json=None, condition_confirmed_json=None,
    )
    async with review_session(tmp_path, [conversion]) as session:
        await require_sources(package, session)


@pytest.mark.asyncio
async def test_mainline_process_name_uses_the_existing_display_alias(tmp_path, rule_package_v2_payload):
    package = RulePackageV2.model_validate(rule_package_v2_payload)
    next(process for process in package.route_catalog.processes if process.process_id == "process_quench").main = True
    conversion = review_row(
        status="draft", source_text="设置为主工序，始终纳入“淬火”工序。",
        condition_candidate_json=None, condition_confirmed_json=None,
    )
    async with review_session(tmp_path, [conversion], process_name="真空淬火") as session:
        await require_sources(package, session)


@pytest.mark.asyncio
async def test_old_user_confirmation_is_rejected_after_a_new_source_is_saved(tmp_path, rule_package_v2_payload):
    package = package_with_confirmation(rule_package_v2_payload, condition_candidate())
    changed = review_row(status="draft", source_text="当材料牌号为 95Cr18 时，纳入淬火工序。")
    async with review_session(tmp_path, [changed]) as session:
        with pytest.raises(HTTPException) as error:
            await require_sources(package, session)
        assert error.value.status_code == 409
        assert "user.quench" in error.value.detail["rule_ids"]


@pytest.mark.asyncio
async def test_missing_confirmation_row_reports_the_source_segment_for_repair(tmp_path, rule_package_v2_payload):
    package = package_with_confirmation(rule_package_v2_payload, condition_candidate())
    async with review_session(tmp_path, []) as session:
        with pytest.raises(HTTPException) as error:
            await require_sources(package, session)

    assert error.value.detail["rule_ids"] == ["user.quench"]
    assert error.value.detail["segment_ids"] == [SEGMENT_ID]
