import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base, configure_sqlite_engine
from app.models.models import KmaiFactorMapping, Project
from app.services.rule_packages.kmai_mapping_registry import (
    KmaiMappingRegistry,
    builtin_factor_catalog,
    builtin_mapping_registry,
    load_effective_mapping_registry,
    manual_factor_key,
    normalize_mapping_value,
)
from app.services.rule_packages.kmai_mapping_contracts import KmaiMappingSnapshot


def _mapping(*, scope, source_value, target_factor_key, project_id=None, status="active", revision=1):
    return KmaiFactorMapping(
        scope=scope,
        project_id=project_id,
        source_field="cad.features",
        source_value=source_value,
        mapping_mode="existing_factor",
        target_factor_key=target_factor_key,
        target_factor_name=target_factor_key,
        target_factor_category="feature",
        status=status,
        revision=revision,
    )


async def _load_registry(tmp_path, project_id, mappings):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'registry.db'}")
    configure_sqlite_engine(engine)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_factory() as db:
            db.add_all(mappings)
            await db.commit()
            registry = await load_effective_mapping_registry(db, project_id)
            return registry
    finally:
        await engine.dispose()


def test_project_mapping_overrides_global_and_builtin(tmp_path):
    async def run():
        project = Project(id=1, name="one")
        registry = await _load_registry(
            tmp_path,
            1,
            [
                project,
                _mapping(
                    scope="global",
                    source_value="\u69fd\u7c7b\u7279\u5f81",
                    target_factor_key="global_slot",
                ),
                _mapping(
                    scope="project",
                    project_id=1,
                    source_value="\u69fd\u7c7b\u7279\u5f81",
                    target_factor_key="project_slot",
                ),
            ],
        )

        resolved = registry.resolve("cad.features", "\u69fd\u7c7b\u7279\u5f81")

        assert resolved is not None
        assert resolved.scope == "project"
        assert resolved.target_factor_key == "project_slot"

    asyncio.run(run())


def test_global_mapping_is_visible_to_other_projects(tmp_path):
    async def run():
        project_one = Project(id=1, name="one")
        project_two = Project(id=2, name="two")
        registry = await _load_registry(
            tmp_path,
            2,
            [
                project_one,
                project_two,
                _mapping(
                    scope="global",
                    source_value="\u69fd\u7c7b\u7279\u5f81",
                    target_factor_key="global_slot",
                ),
                _mapping(
                    scope="project",
                    project_id=1,
                    source_value="\u69fd\u7c7b\u7279\u5f81",
                    target_factor_key="project_one_slot",
                ),
            ],
        )

        resolved = registry.resolve("cad.features", "\u69fd\u7c7b\u7279\u5f81")

        assert resolved is not None
        assert resolved.scope == "global"
        assert resolved.target_factor_key == "global_slot"

    asyncio.run(run())


def test_inactive_mappings_fall_through_to_builtin(tmp_path):
    async def run():
        project = Project(id=1, name="one")
        registry = await _load_registry(
            tmp_path,
            1,
            [
                project,
                _mapping(
                    scope="global",
                    source_value="\u69fd\u7c7b\u7279\u5f81",
                    target_factor_key="inactive_global_slot",
                    status="inactive",
                ),
                _mapping(
                    scope="project",
                    project_id=1,
                    source_value="\u69fd\u7c7b\u7279\u5f81",
                    target_factor_key="inactive_project_slot",
                    status="inactive",
                ),
            ],
        )

        resolved = registry.resolve("cad.features", "\u69fd\u7c7b\u7279\u5f81")

        assert resolved is not None
        assert resolved.scope == "builtin"
        assert resolved.target_factor_key == "has_slot_feature"

    asyncio.run(run())


def test_inactive_project_mapping_falls_through_to_active_global_mapping(tmp_path):
    async def run():
        project = Project(id=1, name="one")
        registry = await _load_registry(
            tmp_path,
            1,
            [
                project,
                _mapping(
                    scope="global",
                    source_value="槽类特征",
                    target_factor_key="global_slot",
                ),
                _mapping(
                    scope="project",
                    project_id=1,
                    source_value="槽类特征",
                    target_factor_key="inactive_project_slot",
                    status="inactive",
                ),
            ],
        )

        resolved = registry.resolve("cad.features", "槽类特征")

        assert resolved is not None
        assert resolved.scope == "global"
        assert resolved.target_factor_key == "global_slot"

    asyncio.run(run())


def test_later_mapping_within_a_scope_overrides_earlier_mapping():
    """Catch lexicographic rather than insertion ordering of persisted identities."""
    registry = KmaiMappingRegistry(
        (
            KmaiMappingSnapshot(
                mapping_id=9,
                mapping_identity="global:9",
                scope="global",
                source_field="cad.features",
                source_value="duplicate value",
                mapping_mode="existing_factor",
                target_factor_key="earlier_target",
                target_factor_name="Earlier",
                target_factor_category="feature",
            ),
            KmaiMappingSnapshot(
                mapping_id=10,
                mapping_identity="global:10",
                scope="global",
                source_field="cad.features",
                source_value="duplicate value",
                mapping_mode="existing_factor",
                target_factor_key="later_target",
                target_factor_name="Later",
                target_factor_category="feature",
            ),
        )
    )

    resolved = registry.resolve("cad.features", "duplicate value")

    assert resolved is not None
    assert resolved.target_factor_key == "later_target"


def test_builtin_snapshots_and_catalog_are_deterministic_and_read_only():
    first_registry = builtin_mapping_registry()
    second_registry = builtin_mapping_registry()

    resolved = first_registry.resolve(" cad.features ", "  槽类特征\t")

    assert resolved is not None
    assert resolved.mapping_identity == "builtin:cad.features:槽类特征"
    assert first_registry.snapshots == second_registry.snapshots
    assert first_registry.signature == second_registry.signature
    assert all(item.read_only for item in builtin_factor_catalog())


def test_mapping_normalization_manual_key_and_signature_are_stable(tmp_path):
    async def run():
        normalized = normalize_mapping_value("  \uff21\uff22\uff23\t feature  ")
        assert normalized == "ABC feature"
        assert manual_factor_key("cad.features", "\uff21\uff22\uff23  feature") == manual_factor_key(
            "cad.features", "ABC feature"
        )

        project = Project(id=1, name="one")
        mapping = _mapping(
            scope="project",
            project_id=1,
            source_value="\uff21\uff22\uff23  feature",
            target_factor_key="first_target",
            revision=1,
        )
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'signature.db'}")
        configure_sqlite_engine(engine)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            async with session_factory() as db:
                db.add_all([project, mapping])
                await db.commit()
                before = await load_effective_mapping_registry(db, 1)
                mapping.target_factor_key = "second_target"
                await db.commit()
                target_changed = await load_effective_mapping_registry(db, 1)
                mapping.revision = 2
                await db.commit()
                revision_changed = await load_effective_mapping_registry(db, 1)
        finally:
            await engine.dispose()

        assert before.resolve("cad.features", "ABC feature").target_factor_key == "first_target"
        assert target_changed.resolve("cad.features", "ABC feature").target_factor_key == "second_target"
        assert before.signature != target_changed.signature
        assert target_changed.signature != revision_changed.signature

    asyncio.run(run())
