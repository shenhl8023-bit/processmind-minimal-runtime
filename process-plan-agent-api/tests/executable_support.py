"""Shared fixture preparation for the executable-before-export workflow."""

from copy import deepcopy
import json
from types import SimpleNamespace

from sqlalchemy import select

from app.models.models import DocumentOperationDetail, GeneratedRoute, NormalizedRouteVersion, Operation
from app.services.rule_packages.executable_revisions import save_revision, latest_revision, latest_route
from app.services.rule_packages.mother_route import load_mother_route
from app.services.rule_packages.planner import plan_route


async def seed_fixed_validation(db, project):
    """Mapping API tests start after a real fixed-route plan has succeeded."""
    route = await latest_route(db, project.id)
    if route is None:
        route = NormalizedRouteVersion(project_id=project.id, version=1, route_json=json.dumps([{
            "id": "fixture.prepare", "normalized_step_name": "准备", "source_operation_ids": [],
            "doc_coverage": {"hit_docs": 1, "total_docs": 1}}]))
        db.add(route)
        await db.flush()
    segments = json.loads(route.route_json)
    # Older workflow fixtures specified source IDs without seeding source rows.
    # Supply those project-owned legacy operations before using the real guard.
    has_details = (await db.execute(select(DocumentOperationDetail.id).where(
        DocumentOperationDetail.project_id == project.id).limit(1))).scalar_one_or_none()
    if not has_details:
        existing = set((await db.execute(select(Operation.id).where(Operation.project_id == project.id))).scalars())
        for segment in segments:
            for source_id in segment.get("source_operation_ids", []):
                if source_id not in existing:
                    db.add(Operation(id=source_id, project_id=project.id, name=segment["normalized_step_name"]))
                    existing.add(source_id)
        await db.flush()
    mother = await load_mother_route(db, project.id, segments)
    previous = await latest_revision(db, project.id)
    request = SimpleNamespace(expected_executable_revision=previous.revision if previous else 0, route_version_id=route.id,
        package_name="mapping-fixture", manifest={"project_id": project.id, "route_version_id": route.id,
            "package_name": "mapping-fixture", "scope": {"type": "project", "key": str(project.id)}}, factor_dictionary=None, input_schema={"fields": []},
        route_catalog={"processes": [{"process_id": s.get("export_process_id") or s["id"],
            "display_name": s["normalized_step_name"], "main": True, "default_sequence": i * 100,
            "source_operation_ids": mother[s.get("export_process_id") or s["id"]]["source_operation_ids"],
            "steps": [{key: step[key] for key in ("step_id", "name", "kind")}
                      for step in mother[s.get("export_process_id") or s["id"]]["steps"]]}
            for i, s in enumerate(segments)]},
        route_rules={"rules": []}, test_cases=[], rule_report_md="# Fixture", created_by="test")
    row = await save_revision(db, project, request)
    from app.services.rule_packages.contracts import RulePackageV2
    plan = plan_route(RulePackageV2.model_validate_json(row.package_json), {})
    db.add(GeneratedRoute(project_id=project.id, executable_revision_id=row.id, input_factors="{}",
                          result_json=json.dumps({"selected_process_ids": plan.selected_process_ids})))
    return row


def generate_current(client, *, json):
    body = deepcopy(json)
    latest = client.get("/api/extract/executable-rule-revisions/latest", params={"project_id": body["project_id"]})
    if latest.status_code == 200:
        body.setdefault("executable_revision_id", latest.json()["id"])
    return client.post("/api/generate/", json=body)


def save_generate_export(client, *, json, include_template_mapping=False):
    """Drive the public lifecycle, returning its first rejected stage unchanged."""
    body = deepcopy(json)
    latest = client.get("/api/extract/executable-rule-revisions/latest", params={"project_id": body["project_id"]})
    body["expected_executable_revision"] = latest.json()["revision"] if latest.status_code == 200 else 0
    saved = client.post("/api/extract/executable-rule-revisions", json=body)
    if saved.status_code != 200:
        return saved
    row = saved.json()
    cases = body.get("test_cases") or []
    inputs = cases[0]["input"] if cases else {}
    metadata = {field["key"]: {"origin": "manual"} for field in row["package"]["input_schema"]["fields"]}
    generated = client.post("/api/generate/", json={"project_id": body["project_id"],
        "expected_workflow_revision": body.get("expected_workflow_revision", 0),
        "executable_revision_id": row["id"], "factor_values": inputs, "input_metadata": metadata})
    if generated.status_code != 200:
        return generated
    return client.post("/api/extract/executable-rule-revisions/{}/export".format(row["id"]), json={
        "project_id": body["project_id"], "expected_workflow_revision": body.get("expected_workflow_revision", 0),
        "expected_content_hash": row["content_hash"], "include_template_mapping": include_template_mapping})


def legacy_archive_fixture(client, *, json):
    """Build a historical three-array archive for compatibility-reader tests.

    This deliberately does not invoke or bypass the current export API. Old
    archives remain supported inputs to the frozen snapshot reader/compiler.
    """
    import asyncio
    from dataclasses import asdict
    import httpx
    from fastapi import HTTPException
    from pydantic import ValidationError
    from sqlalchemy import func
    from app.models.models import FinalizedRulePackage, Project
    from app.schemas.schemas import FinalizedRulePackageSaveRequest
    from app.services.finalized_rule_package_helpers import compile_publication_snapshot, serialize_finalized_rule_package
    from app.services.rule_packages.confirmation_validation import require_confirmed_user_rule_sources
    from app.services.rule_packages.contracts import RulePackageV2
    from app.services.rule_packages.demo_tables import DemoTableError
    from app.services.rule_packages.hashing import rule_package_content_hash
    from app.services.rule_packages.lifecycle import publish_rule_package
    from app.services.rule_packages.template_mapping_requirements import validate_rule_package_template_mapping
    from app.services.rule_packages.validator import validate_rule_package
    from app.routers.extract import _require_current_package_route

    async def build():
        request = FinalizedRulePackageSaveRequest.model_validate(json)
        package = RulePackageV2.model_validate({key: getattr(request, key) for key in
            ("manifest", "factor_dictionary", "input_schema", "route_catalog", "route_rules", "test_cases")})
        validation = validate_rule_package(package)
        if not validation.valid:
            raise HTTPException(422, {"validation": validation.model_dump(mode="json")})
        async with client.lifecycle_session_factory() as db:
            await _require_current_package_route(request.project_id, request.route_version_id,
                                                  package.manifest.route_version_id, db)
            await require_confirmed_user_rule_sources(package, project_id=request.project_id,
                                                      route_version_id=request.route_version_id, db=db)
            blockers = await validate_rule_package_template_mapping(db, package)
            if blockers:
                raise HTTPException(422, {"message": "规则包发布前需完成分组模板映射。", "blockers": [asdict(b) for b in blockers]})
            project = await db.get(Project, request.project_id)
            tables, sources = await compile_publication_snapshot(package, project, db)
            version = (await db.execute(select(func.max(FinalizedRulePackage.version)).where(
                FinalizedRulePackage.project_id == request.project_id))).scalar_one_or_none() or 0
            payload = package.model_dump(mode="json", by_alias=True)
            import json as json_module
            row = FinalizedRulePackage(project_id=request.project_id, route_version_id=request.route_version_id,
                version=version + 1, package_name=request.package_name, status="draft", schema_version="2.0",
                **{key + "_json": json_module.dumps(payload[key], ensure_ascii=False) for key in
                   ("manifest", "factor_dictionary", "input_schema", "route_catalog", "route_rules", "test_cases")},
                demo_tables_json=json_module.dumps(tables, ensure_ascii=False),
                export_sources_json=json_module.dumps(sources, ensure_ascii=False),
                rule_report_md=request.rule_report_md, validation_report_json=validation.model_dump_json(),
                content_hash=rule_package_content_hash(package), created_by=request.created_by)
            db.add(row)
            await db.flush()
            await publish_rule_package(row, db, actor=row.created_by)
            await db.commit()
            return serialize_finalized_rule_package(row).model_dump(mode="json")

    try:
        return httpx.Response(200, json=asyncio.run(build()))
    except HTTPException as exc:
        return httpx.Response(exc.status_code, json={"detail": exc.detail})
    except ValidationError as exc:
        return httpx.Response(422, json={"detail": str(exc)})
    except DemoTableError as exc:
        return httpx.Response(422, json={"detail": {"message": str(exc), "blockers": exc.issues}})
