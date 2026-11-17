"""PM035: durable, project-scoped external identities, isolated from authoring data."""
import asyncio
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, configure_sqlite_engine, get_db
from app.models.models import Project, FinalizedRulePackage
from app.models.public_rule_package_identity import PublicRulePackageIdentity  # registers the additive table


def test_main_registers_identity_route():
    from app.main import create_app

    app = create_app()
    assert 'post' in app.openapi()['paths'].get('/api/extract/public-rule-package-identities', {})


def test_fresh_process_startup_registers_identity_model_before_initializing_database(tmp_path):
    profile = tmp_path / 'profile.json'
    profile.write_text(json.dumps({'edition': 'full', 'template_mapping_enabled': True, 'expires_at': None}))
    database = tmp_path / 'db' / 'startup.db'
    env = dict(os.environ, PROCESSMIND_DATA_DIR=str(tmp_path), PROCESSMIND_DB_PATH=str(database),
               DATABASE_URL='sqlite+aiosqlite:///' + str(database),
               PROCESSMIND_UPLOAD_DIR=str(tmp_path / 'uploads'),
               PROCESSMIND_SETTINGS_PATH=str(tmp_path / 'settings.json'),
               PROCESSMIND_PROFILE_PATH=str(profile))
    script = '''
import sqlite3
from fastapi.testclient import TestClient
from app.main import app
from app.database import Base, DEFAULT_DB_PATH

# Import only the real entrypoint: no direct identity-model import in this process.
assert 'public_rule_package_identities' in Base.metadata.tables
for _ in range(2):
    with TestClient(app) as client:
        with sqlite3.connect(str(DEFAULT_DB_PATH)) as db:
            assert db.execute("SELECT name FROM sqlite_master WHERE name='public_rule_package_identities'").fetchone()
            assert any(row[2] == 'projects' and row[6] == 'CASCADE' for row in db.execute('PRAGMA foreign_key_list(public_rule_package_identities)'))
        response = client.post('/api/extract/public-rule-package-identities', json={
            'finalized_rule_package_id': 999, 'expected_content_hash': 'missing'})
        assert response.status_code == 404, response.text
        assert response.json()['detail'] == '规则包不存在，请重新导出。', response.text
'''
    result = subprocess.run([sys.executable, '-c', script], env=env,
                            cwd=str(Path(__file__).resolve().parents[1]),
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_identity_schema_upgrades_existing_database_without_altering_native_tables(tmp_path):
    async def run():
        engine = create_async_engine('sqlite+aiosqlite:///' + str(tmp_path / 'old.db'))
        async with engine.begin() as conn:
            await conn.execute(text('CREATE TABLE existing_data (id INTEGER PRIMARY KEY, payload TEXT)'))
            await conn.execute(text("INSERT INTO existing_data VALUES (1, 'native-v2-retained')"))
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(Base.metadata.create_all)
            names = await conn.run_sync(lambda sync: inspect(sync).get_table_names())
            assert 'public_rule_package_identities' in names
            assert (await conn.execute(text('SELECT payload FROM existing_data'))).scalar_one() == 'native-v2-retained'
        await engine.dispose()
    asyncio.run(run())


def test_registry_survives_reorder_deletion_restore_new_session_and_database_backup(tmp_path):
    from app.services.rule_packages.public_identities import allocate_public_identities

    async def run():
        location = tmp_path / 'registry.db'
        engine = create_async_engine('sqlite+aiosqlite:///' + str(location))
        configure_sqlite_engine(engine)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with factory() as db:
            db.add_all([Project(id=1, name='one'), Project(id=2, name='two')]); await db.commit()
        async def allocate(identities, project_id=1):
            async with factory() as db:
                result = await allocate_public_identities(db, project_id, identities)
                await db.commit()
                return result
        original = await allocate({'processes': ['long-b', 'long-a'], 'steps': ['s-long-b', 's-long-a'], 'factors': ['project_factor.operation_one.it']})
        assert original['processes'] == {'long-a': 'P001', 'long-b': 'P002'}
        assert original['factors']['project_factor.operation_one.it'] == 'F001'
        expanded = await allocate({'processes': ['long-new', 'long-b', 'long-a'], 'steps': ['s-long-a', 's-long-b'], 'factors': ['project_factor.operation_one.it']})
        assert expanded['processes']['long-new'] == 'P003'
        assert expanded['processes']['long-a'] == original['processes']['long-a']
        removed = await allocate({'processes': ['long-a'], 'steps': [], 'factors': []})
        assert removed['processes']['long-b'] == 'P002'  # Tombstones are retained, never recycled.
        restored = await allocate({'processes': ['long-b'], 'steps': ['s-long-b'], 'factors': []})
        assert restored == expanded
        other_project = await allocate({'processes': ['long-b'], 'steps': [], 'factors': []}, 2)
        assert other_project['processes'] == {'long-b': 'P001'}
        await engine.dispose()
        backup = tmp_path / 'restored.db'
        shutil.copyfile(location, backup)
        restored_engine = create_async_engine('sqlite+aiosqlite:///' + str(backup))
        async with AsyncSession(restored_engine) as db:
            assert await allocate_public_identities(db, 1, {'processes': ['long-a', 'long-b'], 'steps': [], 'factors': []}) == expanded
        await restored_engine.dispose()
    asyncio.run(run())


def test_concurrent_allocations_rollback_and_project_delete(tmp_path):
    from app.models.public_rule_package_identity import PublicRulePackageIdentity
    from app.services.rule_packages.public_identities import allocate_public_identities

    async def run():
        engine = create_async_engine('sqlite+aiosqlite:///' + str(tmp_path / 'concurrent.db'))
        configure_sqlite_engine(engine)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with factory() as db:
            db.add(Project(id=1, name='concurrent')); await db.commit()
        async def allocate(ids):
            async with factory() as db:
                result = await allocate_public_identities(db, 1, {'processes': ids, 'steps': [], 'factors': []})
                await db.commit(); return result
        left, right = await asyncio.gather(allocate(['same', 'left']), allocate(['same', 'right']))
        assert left['processes']['same'] == right['processes']['same']
        async with factory() as db:
            await allocate_public_identities(db, 1, {'processes': ['rolled-back'], 'steps': [], 'factors': []})
            await db.rollback()
        final = await allocate(['last'])
        assert 'rolled-back' not in final['processes']
        assert len(set(final['processes'].values())) == 4
        async with factory() as db:
            await db.delete(await db.get(Project, 1)); await db.commit()
            assert (await db.execute(select(PublicRulePackageIdentity))).scalars().all() == []
            db.add(Project(id=1, name='new-project')); await db.commit()
        assert (await allocate(['same']))['processes'] == {'same': 'P001'}
        await engine.dispose()
    asyncio.run(run())


def test_api_allocates_only_for_exact_validated_frozen_export(tmp_path, rule_package_v2_payload):
    from app.routers.public_rule_package_identities import router
    from app.services.rule_packages.contracts import RulePackageV2
    from app.services.rule_packages.native_publication import compile_native_snapshot

    async def run_setup():
        engine = create_async_engine('sqlite+aiosqlite:///' + str(tmp_path / 'api.db'))
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        package = RulePackageV2.model_validate(rule_package_v2_payload)
        package.manifest.route_version_id = None
        sources = compile_native_snapshot(package, [{'id': 'one'}], 0)
        payload = package.model_dump(mode='json', by_alias=True, exclude_none=True)
        async with factory() as db:
            db.add(Project(id=package.manifest.project_id, name='identity-api'))
            db.add(FinalizedRulePackage(id=1, project_id=package.manifest.project_id, version=1,
                package_name=package.manifest.package_name, schema_version='2.0', status='published',
                content_hash=sources['rule_package_content_hash'], export_sources_json=json.dumps(sources),
                **{key + '_json': json.dumps(payload[key]) for key in ('manifest', 'factor_dictionary', 'input_schema', 'route_catalog', 'route_rules', 'test_cases')}))
            await db.commit()
        return engine, factory, sources['rule_package_content_hash']
    engine, factory, content_hash = asyncio.run(run_setup())
    app = FastAPI(); app.include_router(router)
    async def override():
        async with factory() as db:
            yield db
    app.dependency_overrides[get_db] = override
    client = TestClient(app)
    body = {'finalized_rule_package_id': 1, 'expected_content_hash': content_hash}
    response = client.post('/api/extract/public-rule-package-identities', json=body)
    assert response.status_code == 200, response.text
    assert response.json()['registry']['processes']
    assert client.post('/api/extract/public-rule-package-identities', json=body).json() == response.json()
    assert client.post('/api/extract/public-rule-package-identities', json={**body, 'expected_content_hash': 'stale'}).status_code == 409
    assert client.post('/api/extract/public-rule-package-identities', json={**body, 'finalized_rule_package_id': 999}).status_code == 404
    assert client.post('/api/extract/public-rule-package-identities', json={**body, 'processes': ['untrusted']}).status_code == 422
    async def corrupt_snapshot():
        async with factory() as db:
            row = await db.get(FinalizedRulePackage, 1)
            row.export_sources_json = '{broken-json'
            await db.commit()
    asyncio.run(corrupt_snapshot())
    assert client.post('/api/extract/public-rule-package-identities', json=body).status_code == 409
    client.close(); asyncio.run(engine.dispose())
