"""Per-review edit/confirm races promoted from the round4 independent audit.

Only pytest-owned temporary SQLite databases are written. Tests model two
windows reading the same server review, then submitting different candidates.
"""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json

from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy import select

from app.models.models import NormalizedRouteSegmentRuleReview
from app.services.rule_packages.condition_reviews import condition_source_hash, _manual_process_field_key, serialize_condition_review
from test_executable_revisions import executable_context

BASE = "/api/extract/finalized-rule-packages/rule-conditions"


def processes(body):
    return [{key: process[key] for key in ("process_id", "display_name", "main")}
            for process in body["route_catalog"]["processes"]]


def configuration(body, value="9Cr18"):
    return {"project_id": 12, "route_id": 31, "expected_workflow_revision": 0,
            "segment_id": "segment-1", "process_id": "process_rough_machine", "processes": processes(body),
            "source_text": "按材料安排粗加工", "candidate": {"kind": "process_configuration",
            "configuration": {"process_id": "process_rough_machine", "occurrence": "conditional",
            "when": {"field": "material.grade", "op": "eq", "value": value}, "relations": []},
            "preview": "按材料安排粗加工"}}


def with_token(request, review):
    # Before the fix, there is no exposed token: still exercise the real lost
    # update instead of failing early on an unsupported request property.
    request = deepcopy(request)
    if "review_token" in review:
        request["expected_review_token"] = review["review_token"]
    return request


def stored(factory):
    async def read():
        async with factory() as db:
            row = (await db.execute(select(NormalizedRouteSegmentRuleReview).where(
                NormalizedRouteSegmentRuleReview.segment_id == "segment-1"))).scalar_one()
            return json.loads(row.condition_confirmed_json)
    return asyncio.run(read())


def test_stale_configuration_save_must_not_replace_newer_confirmation(executable_context):
    client, factory, body = executable_context
    original = client.post(BASE + "/configuration", json=configuration(body))
    assert original.status_code == 200, original.text
    opened = original.json()["review"]
    changed = client.post(BASE + "/configuration", json=with_token(configuration(body, "95Cr18"), opened))
    assert changed.status_code == 200, changed.text
    stale = client.post(BASE + "/configuration", json=with_token(configuration(body), opened))
    assert stale.status_code == 409, stale.text
    assert stale.json()["detail"]["code"] == "condition_review_conflict"
    assert stored(factory)["configuration"]["when"]["value"] == "95Cr18"
    assert len(opened["review_token"]) == 64
    assert changed.json()["review"]["review_token"] != opened["review_token"]


def test_same_source_confirmation_must_not_replace_newer_candidate(executable_context):
    client, factory, body = executable_context
    candidate = {"kind": "condition", "when": {"field": "material.grade", "op": "eq", "value": "9Cr18"},
                 "then": {"include_process_ids": ["process_rough_machine"]}, "preview": "按材料安排粗加工"}
    source = candidate["preview"]

    async def seed():
        async with factory() as db:
            row = (await db.execute(select(NormalizedRouteSegmentRuleReview).where(
                NormalizedRouteSegmentRuleReview.segment_id == "segment-1"))).scalar_one()
            row.condition_source_text = source
            row.condition_source_hash = condition_source_hash(source)
            row.condition_status = "pending_confirmation"
            row.condition_candidate_json = json.dumps(candidate)
            await db.commit()
            await db.refresh(row)
            return serialize_condition_review(row).model_dump(mode="json")
    opened = asyncio.run(seed())
    old = with_token({"project_id": 12, "route_id": 31, "expected_workflow_revision": 0,
                      "segment_id": "segment-1", "source_text": source, "source_hash": condition_source_hash(source),
                      "candidate": candidate, "processes": processes(body)}, opened)
    new = deepcopy(old)
    new["candidate"]["when"]["value"] = "95Cr18"
    changed = client.post(BASE + "/confirm", json=new)
    assert changed.status_code == 200, changed.text
    stale = client.post(BASE + "/confirm", json=old)
    assert stale.status_code == 409, stale.text
    assert stored(factory)["when"]["value"] == "95Cr18"


@pytest.mark.parametrize("catalog_alias", [False, True])
def test_manual_endpoint_binds_target_to_saved_segment(executable_context, catalog_alias):
    client, factory, body = executable_context
    initial = client.post(BASE + "/configuration", json=configuration(body, "95Cr18"))
    assert initial.status_code == 200, initial.text
    opened = initial.json()["review"]
    wrong_id = "process_mill_slot"
    key = _manual_process_field_key(wrong_id)
    request = {"project_id": 12, "route_id": 31, "expected_workflow_revision": 0,
               "segment_id": "segment-1", "process_id": wrong_id, "source_text": "是否需要铣槽",
               "processes": processes(body), "candidate": {"kind": "condition",
               "when": {"field": key, "op": "eq", "value": True},
               "then": {"include_process_ids": [wrong_id]}, "field_definitions": [{
               "key": key, "label": "是否需要铣槽", "type": "boolean", "category": "人工安排",
               "operators": ["eq"], "source": "用户直接设定", "allow_custom": False}]}}
    if catalog_alias:
        # Even a valid saved segment ID in the caller's catalog must not let it
        # reinterpret the authoritative export identity of another segment.
        request["process_id"] = "segment-1"
        key = _manual_process_field_key("segment-1")
        request["processes"].append({"process_id": "segment-1", "display_name": "伪造别名"})
        request["candidate"]["when"]["field"] = key
        request["candidate"]["then"]["include_process_ids"] = ["segment-1"]
        request["candidate"]["field_definitions"][0]["key"] = key
    response = client.post(BASE + "/manual", json=with_token(request, opened))
    assert response.status_code == 422, response.text
    assert stored(factory)["configuration"]["when"]["value"] == "95Cr18"


@pytest.mark.parametrize("endpoint", ["draft", "parse", "manual"])
def test_stale_review_token_protects_every_edit_entrypoint(executable_context, monkeypatch, endpoint):
    client, factory, body = executable_context
    first = client.post(BASE + "/configuration", json=configuration(body))
    opened = first.json()["review"]
    changed = client.post(BASE + "/configuration", json=with_token(configuration(body, "95Cr18"), opened))
    assert changed.status_code == 200, changed.text
    request = configuration(body)
    if endpoint == "draft":
        for key in ("process_id", "candidate", "processes"):
            request.pop(key)
        request["source_text"] = "旧窗口的新草稿"
    elif endpoint == "parse":
        request.pop("candidate")
        request["process_name"] = "粗加工"
        request["source_text"] = "旧窗口的解析内容"
    else:
        key = _manual_process_field_key("process_rough_machine")
        request["candidate"] = {"kind": "condition", "when": {"field": key, "op": "eq", "value": True},
                                "then": {"include_process_ids": ["process_rough_machine"]}, "field_definitions": [{
                                "key": key, "label": "是否需要粗加工", "category": "人工安排", "type": "boolean",
                                "operators": ["eq"], "source": "用户直接设定", "allow_custom": False}]}
    async def local_parser(*args, **kwargs):
        return None, 0.0, ["隔离解析"]
    monkeypatch.setattr("app.services.rule_packages.condition_reviews.parse_rule_condition", local_parser)
    response = client.post(BASE + "/" + endpoint, json=with_token(request, opened))
    assert response.status_code == 409, response.text
    assert stored(factory)["configuration"]["when"]["value"] == "95Cr18"


def test_first_configuration_can_create_review_and_empty_token_rejects_later_writer(executable_context):
    from sqlalchemy import delete
    client, factory, body = executable_context

    async def remove_review():
        async with factory() as db:
            await db.execute(delete(NormalizedRouteSegmentRuleReview).where(
                NormalizedRouteSegmentRuleReview.segment_id == "segment-1"))
            await db.commit()
    asyncio.run(remove_review())
    request = {**configuration(body), "expected_review_token": ""}
    saved = client.post(BASE + "/configuration", json=request)
    assert saved.status_code == 200, saved.text
    assert len(saved.json()["review"]["review_token"]) == 64
    stale = client.post(BASE + "/configuration", json=request)
    assert stale.status_code == 409, stale.text


def test_conditional_write_rejects_stale_loaded_row_even_for_legacy_request(executable_context, monkeypatch):
    from fastapi import HTTPException
    from app.services.rule_packages import condition_reviews as service
    from app.services.rule_packages.condition_contracts import ManualRuleConditionRequest
    client, factory, body = executable_context
    initial = client.post(BASE + "/configuration", json=configuration(body))
    assert initial.status_code == 200, initial.text
    original_load = service._load_route_and_review

    async def interleave():
        async with factory() as stale_db, factory() as newer_db:
            route, stale_row = await original_load(12, 31, "segment-1", stale_db)
            newer = await service.set_process_configuration_review(
                ManualRuleConditionRequest.model_validate(configuration(body, "95Cr18")), newer_db)
            assert newer.review.confirmed.configuration.when.value == "95Cr18"

            async def retained_snapshot(*args):
                return route, stale_row
            monkeypatch.setattr(service, "_load_route_and_review", retained_snapshot)
            with pytest.raises(HTTPException) as caught:
                await service.set_process_configuration_review(
                    ManualRuleConditionRequest.model_validate(configuration(body)), stale_db)
            assert caught.value.status_code == 409
    asyncio.run(interleave())
    assert stored(factory)["configuration"]["when"]["value"] == "95Cr18"


def test_successful_rule_cas_invalidates_existing_validation_generation_and_publication(executable_context):
    from app.models.models import ExecutableRuleRevision, GeneratedRoute, FinalizedRulePackage
    from test_executable_revisions import save, generate, export
    client, factory, body = executable_context
    revision = save(client, body)
    generated = generate(client, revision)
    assert generated.status_code == 200, generated.text
    published = export(client, revision)
    assert published.status_code == 200, published.text
    changed = client.post(BASE + "/configuration", json=configuration(body))
    assert changed.status_code == 200, changed.text

    async def read():
        async with factory() as db:
            executable = await db.get(ExecutableRuleRevision, revision["id"])
            publication = await db.get(FinalizedRulePackage, published.json()["id"])
            generations = (await db.execute(select(GeneratedRoute))).scalars().all()
            return executable.status, publication.status, generations
    status, publication, generations = asyncio.run(read())
    assert status == "invalid"
    assert publication == "superseded"
    assert generations == []


def test_tokens_allow_batching_different_segments_without_workflow_revision_bump(executable_context):
    from app.models.models import Project
    client, factory, body = executable_context

    async def opened_reviews():
        async with factory() as db:
            rows = (await db.execute(select(NormalizedRouteSegmentRuleReview))).scalars().all()
            return {row.segment_id: serialize_condition_review(row).model_dump(mode="json") for row in rows}
    opened = asyncio.run(opened_reviews())
    for segment, process in [("segment-1", "process_rough_machine"), ("segment-2", "process_mill_slot")]:
        request = configuration(body)
        request.update(segment_id=segment, process_id=process)
        request["candidate"]["configuration"]["process_id"] = process
        result = client.post(BASE + "/configuration", json=with_token(request, opened[segment]))
        assert result.status_code == 200, result.text

    async def workflow_revision():
        async with factory() as db:
            return (await db.get(Project, 12)).workflow_revision
    assert asyncio.run(workflow_revision()) == 0


def test_structured_always_handoff_remains_pending_until_explicit_token_confirmation(executable_context, monkeypatch):
    client, factory, body = executable_context
    candidate = {"kind": "process_configuration", "configuration": {
        "process_id": "process_rough_machine", "occurrence": "always", "when": None, "relations": []},
        "preview": "始终安排粗加工"}
    source = candidate["preview"]

    async def seed():
        async with factory() as db:
            row = (await db.execute(select(NormalizedRouteSegmentRuleReview).where(
                NormalizedRouteSegmentRuleReview.segment_id == "segment-1"))).scalar_one()
            row.analysis_draft_json = json.dumps({"scope": "全部零件", "object": "粗加工", "condition_text": source,
                                                 "candidate": candidate, "status": "confirmed"})
            await db.commit()
            await db.refresh(row)
            return serialize_condition_review(row).model_dump(mode="json")
    opened = asyncio.run(seed())

    async def forbidden_parser(*args, **kwargs):
        pytest.fail("A confirmed structured answer must not invoke inference")
    monkeypatch.setattr("app.services.rule_packages.condition_reviews.parse_rule_condition", forbidden_parser)
    request = {"project_id": 12, "route_id": 31, "expected_workflow_revision": 0,
               "segment_id": "segment-1", "process_id": "process_rough_machine", "process_name": "粗加工",
               "source_text": source, "processes": processes(body)}
    parsed = client.post(BASE + "/parse", json=with_token(request, opened))
    assert parsed.status_code == 200, parsed.text
    pending = parsed.json()["review"]
    assert pending["status"] == "pending_confirmation"
    assert pending["candidate"]["configuration"]["occurrence"] == "always"
    assert pending["confirmed"] is None
    assert pending["review_token"] != opened["review_token"]
    confirm = {key: value for key, value in request.items() if key not in {"process_id", "process_name"}}
    confirm.update(source_hash=pending["source_hash"], candidate=pending["candidate"])
    confirmed = client.post(BASE + "/confirm", json=with_token(confirm, pending))
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["review"]["status"] == "confirmed"
    assert stored(factory)["configuration"]["occurrence"] == "always"


async def _persisted_review(factory):
    async with factory() as db:
        return (await db.execute(select(NormalizedRouteSegmentRuleReview).where(
            NormalizedRouteSegmentRuleReview.segment_id == "segment-1"))).scalar_one()


def _control_review_clock(monkeypatch, step_seconds):
    """Replace only the wall clock; tokens, HTTP requests and DB writes stay real."""
    instant = datetime.now(timezone.utc)
    calls = 0

    class ControlledClock(datetime):
        @classmethod
        def now(cls, tz=None):
            nonlocal calls
            current = instant + timedelta(seconds=step_seconds * calls)
            calls += 1
            return current if tz is not None else current.replace(tzinfo=None)

    monkeypatch.setattr("app.services.rule_packages.condition_reviews.datetime", ControlledClock)


@pytest.mark.parametrize("clock_step", [0, -1], ids=["repeated", "backward"])
def test_repeated_clock_value_must_not_revalidate_an_old_review_token(executable_context, monkeypatch, clock_step):
    """Promoted independent audit: valid A -> B -> A must invalidate old A."""
    client, factory, body = executable_context
    _control_review_clock(monkeypatch, clock_step)
    opened = serialize_condition_review(asyncio.run(_persisted_review(factory))).model_dump(mode="json")
    first = client.post(BASE + "/configuration", json=with_token(configuration(body, "9Cr18"), opened))
    assert first.status_code == 200, first.text
    first_review = first.json()["review"]
    timestamps = [asyncio.run(_persisted_review(factory)).updated_at]
    second = client.post(BASE + "/configuration", json=with_token(configuration(body, "95Cr18"), first_review))
    assert second.status_code == 200, second.text
    timestamps.append(asyncio.run(_persisted_review(factory)).updated_at)
    third = client.post(BASE + "/configuration", json=with_token(configuration(body, "9Cr18"), second.json()["review"]))
    assert third.status_code == 200, third.text
    timestamps.append(asyncio.run(_persisted_review(factory)).updated_at)
    stale = client.post(BASE + "/configuration", json=with_token(configuration(body, "stale old-window edit"), first_review))
    assert stale.status_code == 409, {
        "stale_http_status": stale.status_code,
        "first_token_equals_third_token": first_review["review_token"] == third.json()["review"]["review_token"],
        "persisted": stored(factory)["configuration"]["when"]["value"],
    }
    assert stored(factory)["configuration"]["when"]["value"] == "9Cr18"
    assert first_review["review_token"] != third.json()["review"]["review_token"]
    assert timestamps[0] < timestamps[1] < timestamps[2]


@pytest.mark.parametrize("clock_step", [0, -1], ids=["repeated", "backward"])
def test_repeated_clock_value_must_keep_newer_parse_as_owner(executable_context, monkeypatch, clock_step):
    """Let the old model finish first while the newer same-text parse is waiting."""
    from app.services.rule_packages.condition_contracts import RuleConditionCandidate
    from app.services.rule_packages import condition_reviews as service
    client, factory, body = executable_context
    _control_review_clock(monkeypatch, clock_step)

    async def parser_context():
        return "isolated-clock-parser", {}

    monkeypatch.setattr(service, "_active_condition_parser_context", parser_context)

    async def interleave():
        entered = [asyncio.Event(), asyncio.Event()]
        release = [asyncio.Event(), asyncio.Event()]
        calls = 0

        async def parser(*_args, **_kwargs):
            nonlocal calls
            index = calls
            calls += 1
            entered[index].set()
            await release[index].wait()
            candidate = configuration(body, "old result" if index == 0 else "new result")["candidate"]
            return RuleConditionCandidate.model_validate(candidate), 0.9, []

        monkeypatch.setattr(service, "parse_rule_condition", parser)
        request = configuration(body)
        request.pop("candidate")
        request["process_name"] = "粗加工"
        first_row = await _persisted_review(factory)
        async with AsyncClient(transport=ASGITransport(app=client.app), base_url="http://isolated-test") as http:
            first = asyncio.create_task(http.post(BASE + "/parse", json=with_token(
                request, serialize_condition_review(first_row).model_dump(mode="json"))))
            second = None
            try:
                await asyncio.wait_for(entered[0].wait(), timeout=4)
                first_parsing = await _persisted_review(factory)
                second = asyncio.create_task(http.post(BASE + "/parse", json=with_token(
                    request, serialize_condition_review(first_parsing).model_dump(mode="json"))))
                await asyncio.wait_for(entered[1].wait(), timeout=4)
                second_parsing = await _persisted_review(factory)
                release[0].set()
                old_response = await asyncio.wait_for(first, timeout=4)
                assert old_response.status_code == 200, old_response.text
                release[1].set()
                new_response = await asyncio.wait_for(second, timeout=4)
                assert new_response.status_code == 200, new_response.text
                saved = await _persisted_review(factory)
                assert json.loads(saved.condition_candidate_json)["configuration"]["when"]["value"] == "new result"
                assert new_response.json()["review"]["candidate"]["configuration"]["when"]["value"] == "new result"
                assert old_response.json()["review"]["status"] == "parsing"
                assert first_row.updated_at < first_parsing.updated_at < second_parsing.updated_at < saved.updated_at
            finally:
                for gate in release:
                    gate.set()
                for task in (first, second):
                    if task and not task.done():
                        task.cancel()
                        await asyncio.gather(task, return_exceptions=True)

    asyncio.run(interleave())


def test_parse_cannot_claim_another_revision_during_commit_refresh_gap(executable_context, monkeypatch):
    """A response refresh may see a later writer without transferring ownership."""
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.services.rule_packages.condition_contracts import RuleConditionCandidate
    from app.services.rule_packages import condition_reviews as service
    client, factory, body = executable_context
    original_refresh = AsyncSession.refresh

    async def parser_context():
        return "isolated-refresh-gap-parser", {}

    monkeypatch.setattr(service, "_active_condition_parser_context", parser_context)

    async def interleave():
        gap_entered, release_gap = asyncio.Event(), asyncio.Event()
        older_entered, newer_entered = asyncio.Event(), asyncio.Event()
        release_older, release_newer = asyncio.Event(), asyncio.Event()
        intercepted = False

        async def delayed_refresh(db, instance, *args, **kwargs):
            nonlocal intercepted
            if (isinstance(instance, NormalizedRouteSegmentRuleReview)
                    and instance.condition_status == "parsing" and not intercepted):
                intercepted = True
                gap_entered.set()
                await release_gap.wait()
            return await original_refresh(db, instance, *args, **kwargs)

        async def parser(_source, _process, process_name, *_args, **_kwargs):
            newer = process_name == "newer request"
            (newer_entered if newer else older_entered).set()
            await (release_newer if newer else release_older).wait()
            candidate = configuration(body, "new result" if newer else "old result")["candidate"]
            return RuleConditionCandidate.model_validate(candidate), 0.9, []

        monkeypatch.setattr(AsyncSession, "refresh", delayed_refresh)
        monkeypatch.setattr(service, "parse_rule_condition", parser)
        request = configuration(body)
        request.pop("candidate")
        request["process_name"] = "older request"
        opened = serialize_condition_review(await _persisted_review(factory)).model_dump(mode="json")
        async with AsyncClient(transport=ASGITransport(app=client.app), base_url="http://isolated-test") as http:
            older = asyncio.create_task(http.post(BASE + "/parse", json=with_token(request, opened)))
            newer = None
            try:
                await asyncio.wait_for(gap_entered.wait(), timeout=4)
                latest = serialize_condition_review(await _persisted_review(factory)).model_dump(mode="json")
                newer_body = {**request, "process_name": "newer request"}
                newer = asyncio.create_task(http.post(BASE + "/parse", json=with_token(newer_body, latest)))
                await asyncio.wait_for(newer_entered.wait(), timeout=4)
                release_gap.set()
                await asyncio.wait_for(older_entered.wait(), timeout=4)
                release_older.set()
                older_response = await asyncio.wait_for(older, timeout=4)
                assert older_response.status_code == 200, older_response.text
                assert older_response.json()["review"]["status"] == "parsing"
                release_newer.set()
                newer_response = await asyncio.wait_for(newer, timeout=4)
                assert newer_response.status_code == 200, newer_response.text
                saved = await _persisted_review(factory)
                assert json.loads(saved.condition_candidate_json)["configuration"]["when"]["value"] == "new result"
                assert newer_response.json()["review"]["candidate"]["configuration"]["when"]["value"] == "new result"
            finally:
                for gate in (release_gap, release_older, release_newer):
                    gate.set()
                for task in (older, newer):
                    if task and not task.done():
                        task.cancel()
                        await asyncio.gather(task, return_exceptions=True)

    asyncio.run(interleave())
