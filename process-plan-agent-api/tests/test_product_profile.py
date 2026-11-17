"""Product limits must apply to the actual API, including an already running server."""
import json
import asyncio
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def product_profile(monkeypatch, tmp_path):
    from app.core import product_profile as product

    path = tmp_path / 'product-profile.json'
    path.write_text(json.dumps({
        'edition': 'basic-trial',
        'template_mapping_enabled': False,
        'expires_at': '2026-12-31T00:00:00+08:00',
    }), encoding='utf-8')
    monkeypatch.setenv('PROCESSMIND_PROFILE_PATH', str(path))
    monkeypatch.setenv('PROCESSMIND_FEATURES_PATH', str(tmp_path / 'product-features.json'))
    (tmp_path / 'product-features.json').write_text('{}', encoding='utf-8')
    product.get_product_profile.cache_clear()
    yield product, path
    product.get_product_profile.cache_clear()


@pytest.mark.parametrize('now, expired', [
    ('2026-12-30T15:59:59.999999+00:00', False),
    ('2026-12-30T16:00:00+00:00', True),
    ('2027-01-01T00:00:00+00:00', True),
])
def test_trial_expires_after_december_30_in_shanghai(product_profile, now, expired):
    product, _ = product_profile
    assert product.get_product_profile().is_expired(datetime.fromisoformat(now)) is expired


def test_running_server_stops_every_business_method_at_expiry(product_profile, monkeypatch):
    product, _ = product_profile
    from app.main import create_app

    now = [datetime(2026, 12, 30, 15, 59, tzinfo=timezone.utc)]
    monkeypatch.setattr(product, 'utc_now', lambda: now[0])
    app = create_app()
    calls = []

    @app.api_route('/api/trial-probe', methods=['GET', 'POST', 'DELETE'])
    async def probe():
        calls.append('called')
        return {'ok': True}

    client = TestClient(app)
    assert client.get('/api/trial-probe').status_code == 200
    now[0] = datetime(2026, 12, 30, 16, tzinfo=timezone.utc)
    for method in ('get', 'post', 'delete'):
        response = getattr(client, method)('/api/trial-probe')
        assert response.status_code == 403
        assert response.json()['detail']['code'] == 'trial_expired'
    assert calls == ['called']
    assert client.get('/api/projects/').status_code == 403
    assert client.get('/docs').status_code == 403
    assert client.get('/openapi.json').status_code == 403
    assert client.get('/api/startup-ping').json()['status'] == 'ok'
    status = client.get('/api/product-status').json()
    assert status['edition'] == 'basic-trial'
    assert status['template_mapping_enabled'] is False
    assert status['expired'] is True
    assert status['expires_at'] == '2026-12-31T00:00:00+08:00'
    assert status['server_time'] == '2026-12-30T16:00:00+00:00'


def test_expired_server_still_serves_lock_screen_assets(product_profile, monkeypatch, tmp_path):
    product, _ = product_profile
    from app.main import create_app

    monkeypatch.setattr(product, 'utc_now', lambda: datetime(2027, 1, 1, tzinfo=timezone.utc))
    frontend = tmp_path / 'frontend'
    (frontend / 'assets').mkdir(parents=True)
    (frontend / 'index.html').write_text('<html>trial shell</html>')
    (frontend / 'assets' / 'app.js').write_text('/* bundled app */')
    client = TestClient(create_app(frontend_dir=frontend))
    assert client.get('/').status_code == 200
    assert client.get('/assets/app.js').status_code == 200
    assert client.get('/generate', headers={'Accept': 'text/html'}).status_code == 200
    assert client.get('/api/extract/finalized-rule-package/1').status_code == 403


def test_basic_edition_rejects_template_endpoints_before_expiry(product_profile, monkeypatch):
    product, _ = product_profile
    from app.main import create_app

    monkeypatch.setattr(product, 'utc_now', lambda: datetime(2026, 11, 1, tzinfo=timezone.utc))
    client = TestClient(create_app())
    for path in ('/api/extract/template-group-mappings/suggest', '/api/extract/template-step-mappings/suggest',
                 '/api/extract/template-process-precisions/suggest', '/api/extract/group-templates/preview',
                 '/api/extract/group-templates/current'):
        response = client.post(path)
        assert response.status_code == 403
        assert response.json()['detail']['code'] == 'feature_disabled'


def test_full_profile_remains_usable_after_trial_date(product_profile, monkeypatch):
    product, path = product_profile
    from app.main import create_app

    path.write_text(json.dumps({'edition': 'full', 'template_mapping_enabled': True, 'expires_at': None}))
    product.get_product_profile.cache_clear()
    monkeypatch.setattr(product, 'utc_now', lambda: datetime(2027, 1, 1, tzinfo=timezone.utc))
    app = create_app()

    @app.get('/api/full-probe')
    async def probe():
        return {'ok': True}

    client = TestClient(app)
    assert client.get('/api/full-probe').status_code == 200
    assert client.get('/api/product-status').json()['expired'] is False
    # Full edition still reaches request validation instead of the feature guard.
    assert client.post('/api/extract/template-process-precisions/suggest').status_code == 422


@pytest.mark.parametrize('edition', ['full', 'basic-trial'])
def test_frontend_receives_delivery_edition_without_a_status_request(product_profile, monkeypatch, tmp_path, edition):
    product, path = product_profile
    from app.main import create_app

    if edition == 'full':
        path.write_text(json.dumps({'edition': 'full', 'template_mapping_enabled': True, 'expires_at': None}))
        product.get_product_profile.cache_clear()
    monkeypatch.setattr(product, 'utc_now', lambda: datetime(2026, 11, 1, tzinfo=timezone.utc))
    frontend = tmp_path / 'frontend'
    (frontend / 'assets').mkdir(parents=True)
    original = '<html><head><meta name="processmind-edition" content="full" /></head><body>app</body></html>'
    (frontend / 'index.html').write_text(original, encoding='utf-8')
    (frontend / 'assets' / 'app.js').write_text('/* unchanged asset */', encoding='utf-8')
    client = TestClient(create_app(frontend_dir=frontend))
    for url in ['/', '/index.html', '/upload', '/generate']:
        response = client.get(url, headers={'Accept': 'text/html'})
        assert response.status_code == 200
        assert '<meta name="processmind-edition" content="{}" />'.format(edition) in response.text
        assert response.headers['cache-control'] == 'no-store'
    assert client.get('/assets/app.js').text == '/* unchanged asset */'
    assert (frontend / 'index.html').read_text(encoding='utf-8') == original


@pytest.mark.parametrize('contents', ['{}', '{invalid', '{"edition":"basic-trial","template_mapping_enabled":false,"expires_at":null}',
                                      '{"edition":"full","template_mapping_enabled":false,"expires_at":null}',
                                      '{"edition":"basic-trial","template_mapping_enabled":true,"expires_at":"2026-12-31T00:00:00+08:00"}',
                                      '{"edition":"basic-trial","template_mapping_enabled":false,"expires_at":"2026-12-31T00:00:00"}'])
def test_invalid_profile_never_silently_unlocks_software(product_profile, contents):
    product, path = product_profile
    path.write_text(contents)
    product.get_product_profile.cache_clear()
    with pytest.raises(RuntimeError, match='产品配置'):
        product.get_product_profile()


@pytest.mark.parametrize('enabled', [False, True])
def test_full_visibility_is_independent_of_license_and_expiry(product_profile, monkeypatch, enabled, rule_package_v2):
    product, path = product_profile
    from app.main import create_app
    from app.services.rule_packages.native_publication import package_for_product_profile

    path.write_text(json.dumps({'edition': 'full', 'template_mapping_enabled': True, 'expires_at': None}))
    path.with_name('product-features.json').write_text(json.dumps({'template_mapping_enabled': enabled}))
    product.get_product_profile.cache_clear()
    monkeypatch.setattr(product, 'utc_now', lambda: datetime(2027, 1, 1, tzinfo=timezone.utc))
    client = TestClient(create_app())
    status = client.get('/api/product-status').json()
    assert status['template_mapping_enabled'] is enabled
    assert status['edition'] == 'full'
    assert status['expired'] is False and status['expires_at'] is None
    # UI hiding must neither block mapping APIs nor strip metadata on compile/save.
    assert product.get_product_profile().template_mapping_enabled is True
    assert client.post('/api/extract/template-process-precisions/suggest').status_code == 422
    rule_package_v2.manifest.compiled_from.template_ids = ['saved-template']
    assert package_for_product_profile(rule_package_v2).manifest.compiled_from.template_ids == ['saved-template']


def test_visibility_is_cached_until_restart_and_reenable_keeps_license(product_profile):
    product, path = product_profile
    path.write_text(json.dumps({'edition': 'full', 'template_mapping_enabled': True, 'expires_at': None}))
    features = path.with_name('product-features.json')
    features.write_text('{"template_mapping_enabled":false}')
    product.get_product_profile.cache_clear()
    assert product.get_product_profile().status()['template_mapping_enabled'] is False
    features.write_text('{"template_mapping_enabled":true}')
    assert product.get_product_profile().status()['template_mapping_enabled'] is False
    product.get_product_profile.cache_clear()
    assert product.get_product_profile().status()['template_mapping_enabled'] is True


def test_default_optional_features_path_is_deployment_root_and_missing_means_visible(product_profile, monkeypatch, tmp_path):
    product, path = product_profile
    path.write_text(json.dumps({'edition': 'full', 'template_mapping_enabled': True, 'expires_at': None}))
    monkeypatch.delenv('PROCESSMIND_FEATURES_PATH')
    monkeypatch.setattr(product, 'PROJECT_ROOT', tmp_path)
    features = path.with_name('product-features.json')
    features.unlink()
    product.get_product_profile.cache_clear()
    assert product.get_product_profile().status()['template_mapping_enabled'] is True
    features.write_text('{"template_mapping_enabled":false}')
    product.get_product_profile.cache_clear()
    assert product.get_product_profile().status()['template_mapping_enabled'] is False


def test_relative_features_override_is_relative_to_deployment_root(product_profile, monkeypatch, tmp_path):
    product, path = product_profile
    path.write_text(json.dumps({'edition': 'full', 'template_mapping_enabled': True, 'expires_at': None}))
    monkeypatch.setattr(product, 'PROJECT_ROOT', tmp_path)
    monkeypatch.setenv('PROCESSMIND_FEATURES_PATH', 'product-features.json')
    path.with_name('product-features.json').write_text('\ufeff{"template_mapping_enabled":false}', encoding='utf-8')
    product.get_product_profile.cache_clear()
    assert product.get_product_profile().status()['template_mapping_enabled'] is False


@pytest.mark.parametrize('contents', ['{invalid', '[]', '{"template_mapping_enabled":"false"}',
                                      '{"template_mapping_enabled":0}', '{"other":false}'])
def test_invalid_features_are_reported_instead_of_silently_ignored(product_profile, contents):
    product, path = product_profile
    path.with_name('product-features.json').write_text(contents)
    product.get_product_profile.cache_clear()
    with pytest.raises(RuntimeError, match='功能配置'):
        product.get_product_profile()


def test_explicit_missing_features_file_is_a_configuration_error(product_profile):
    product, path = product_profile
    path.with_name('product-features.json').unlink()
    product.get_product_profile.cache_clear()
    with pytest.raises(RuntimeError, match='功能配置'):
        product.get_product_profile()


def test_features_cannot_unlock_trial_capabilities(product_profile, monkeypatch):
    product, path = product_profile
    from app.main import create_app

    path.with_name('product-features.json').write_text('{"template_mapping_enabled":true}')
    product.get_product_profile.cache_clear()
    monkeypatch.setattr(product, 'utc_now', lambda: datetime(2026, 11, 1, tzinfo=timezone.utc))
    client = TestClient(create_app())
    assert client.get('/api/product-status').json()['template_mapping_enabled'] is False
    assert client.post('/api/extract/template-process-precisions/suggest').status_code == 403


def test_visibility_restart_preserves_saved_mapping_and_published_package(product_profile, tmp_path):
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from app.database import Base, get_db
    from app.main import create_app
    from app.models.models import FinalizedRulePackage, Project
    from app.services.group_template_xml import parse_group_template_xml
    from app.services.project_group_templates import commit_project_group_template, replace_project_group_mappings

    product, path = product_profile
    path.write_text(json.dumps({'edition': 'full', 'template_mapping_enabled': True, 'expires_at': None}))
    product.get_product_profile.cache_clear()
    engine = create_async_engine('sqlite+aiosqlite:///%s' % (tmp_path / 'saved-mapping.db'))
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    xml = '''<Kmsoft><Item type="Part_Template"/><Item type="Group_Template"/>
      <Item type="Part" filename="fixture.prt"><Item type="Group" id="hole">
      <Params><param name="名称" value="hole"/>
      <param name="特征选择" value="hole"/></Params>
      </Item></Item></Kmsoft>'''.encode('utf-8')

    async def seed():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with sessions() as db:
            project = Project(name='visibility-persistence')
            db.add(project)
            await db.flush()
            await commit_project_group_template(db, project.id, parse_group_template_xml('saved.xml', xml), expected_revision=0)
            await replace_project_group_mappings(db, project.id, [{
                'source_operation_id': 11, 'alias': 'saved-hole', 'template_group_path': ['hole'],
            }], expected_revision=1)
            package = FinalizedRulePackage(project_id=project.id, package_name='saved-package',
                                           manifest_json='{"saved":true}', content_hash='unchanged')
            db.add(package)
            await db.commit()
            return project.id, package.id

    async def override_get_db():
        async with sessions() as db:
            yield db

    async def package_snapshot(package_id):
        async with sessions() as db:
            row = await db.get(FinalizedRulePackage, package_id)
            return row.package_name, row.manifest_json, row.content_hash, row.status

    try:
        project_id, package_id = asyncio.run(seed())
        expected_package = asyncio.run(package_snapshot(package_id))
        initial = create_app()
        initial.dependency_overrides[get_db] = override_get_db
        response = TestClient(initial).get('/api/extract/group-templates/current', params={'project_id': project_id})
        assert response.status_code == 200, response.text
        saved_template = response.json()
        assert saved_template['mappings'][0]['alias'] == 'saved-hole'
        for enabled in [False, True]:
            path.with_name('product-features.json').write_text(json.dumps({'template_mapping_enabled': enabled}))
            product.get_product_profile.cache_clear()  # Equivalent to a new deployment process.
            app = create_app()
            app.dependency_overrides[get_db] = override_get_db
            client = TestClient(app)
            assert client.get('/api/product-status').json()['template_mapping_enabled'] is enabled
            current = client.get('/api/extract/group-templates/current', params={'project_id': project_id})
            assert current.status_code == 200, current.text
            assert current.json() == saved_template
            assert asyncio.run(package_snapshot(package_id)) == expected_package
    finally:
        asyncio.run(engine.dispose())
