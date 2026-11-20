"""Public export and the shipped receiver must retain conditional requiredness."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import runpy

import pytest

from app.services.rule_packages.demo_tables import DemoTableError, validate_demo_tables
from app.services.rule_packages.contracts import RulePackageV2
from app.services.rule_packages.input_validation import canonicalize_inputs, validate_inputs
from app.services.rule_packages.planner import plan_route


READER = Path(__file__).resolve().parents[2] / 'integrations/kmai/config_route_engine.py'
spec = importlib.util.spec_from_file_location('conditional_required_receiver', READER)
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)


def tables():
    fields = []
    for prefix in ('F01', 'F02'):
        when = {'field': prefix + '0', 'op': 'eq', 'value': True}
        # Put the controlling field last to catch checks during the first pass.
        fields.extend([
            {'key': prefix + '1', 'label': prefix + '方位', 'type': 'enum', 'options': ['A侧', 'B侧'],
             'source': 'manual_defaults.' + prefix + '1', 'visible': True, 'default': None, 'required_when': when},
            {'key': prefix + '2', 'label': prefix + 'IT', 'type': 'int', 'validation': {'min': 5, 'max': 10},
             'source': 'manual_defaults.' + prefix + '2', 'visible': True, 'default': None, 'required_when': when},
            {'key': prefix + '3', 'label': prefix + 'Ra', 'type': 'number', 'validation': {'min': 5e-324},
             'source': 'manual_defaults.' + prefix + '3', 'visible': True, 'default': None, 'required_when': when},
            {'key': prefix + '0', 'label': prefix + '特征', 'type': 'bool',
             'source': 'manual_defaults.' + prefix + '0', 'visible': True, 'default': None},
        ])
    return {'factor_table': fields,
            'full_route_table': [
                {'process_id': 'P001', 'process_name': '下料', 'process_type': '辅助工序', 'precision': '辅助工序', 'steps': []},
                {'process_id': 'P002', 'process_name': '磨孔', 'process_type': '加工工序', 'precision': '精加工', 'steps': []},
            ], 'rule_table': [
                {'target': 'P001', 'required': True},
                {'target': 'P002', 'when': {'all': [
                    {'field': 'F010', 'op': 'eq', 'value': True},
                    {'field': 'F011', 'op': 'eq', 'value': 'A侧'},
                    {'field': 'F012', 'op': 'lte', 'value': 7},
                    {'field': 'F013', 'op': 'lte', 'value': 0.8},
                ]}},
            ]}


def engine(value=None):
    value = value or tables()
    return reader.ConfigRouteEngine(value['factor_table'], value['full_route_table'], value['rule_table'])


def selected(prefix='F01'):
    return {prefix + '0': True, prefix + '1': 'A侧', prefix + '2': 7, prefix + '3': 0.8}


def test_public_validator_accepts_conditional_requirements():
    validate_demo_tables(tables())


@pytest.mark.parametrize('flags', [{}, {'F010': False}, {'F010': None}, {'F010': False, 'F020': False}])
def test_unselected_features_do_not_require_parameters(flags):
    assert [row['process_name'] for row in engine().run({'factor_overrides': flags})['route']] == ['下料']


@pytest.mark.parametrize('suffix', ['1', '2', '3'])
@pytest.mark.parametrize('empty', [None, ''])
def test_missing_selected_parameter_is_rejected(suffix, empty):
    facts = selected()
    facts['F01' + suffix] = empty
    with pytest.raises(ValueError):
        engine().run({'factor_overrides': facts})


@pytest.mark.parametrize('suffix', ['1', '2', '3'])
def test_absent_selected_parameter_is_rejected_and_other_feature_cannot_supply_it(suffix):
    facts = {**selected(), **selected('F02')}
    del facts['F01' + suffix]
    with pytest.raises(ValueError, match='F01' + suffix):
        engine().run({'factor_overrides': facts})


def test_complete_inputs_use_forward_reference_and_preserve_route_rules():
    assert [row['process_name'] for row in engine().run({'factor_overrides': selected()})['route']] == ['下料', '磨孔']
    facts = {**selected(), 'F012': 8}
    assert [row['process_name'] for row in engine().run({'factor_overrides': facts})['route']] == ['下料']


def test_parameter_preview_preserves_requirements_without_rejecting_incomplete_inputs():
    output = engine().run({'factor_overrides': {'F010': True}}, parameters=True)
    assert output['factor_table'][0]['required_when'] == {'field': 'F010', 'op': 'eq', 'value': True}


@pytest.mark.parametrize('key,bad', [('F010', 'true'), ('F011', 1), ('F012', 6.5), ('F012', 4), ('F012', 11), ('F013', 0), ('F013', -1)])
def test_type_and_precision_checks_still_apply(key, bad):
    with pytest.raises(ValueError):
        engine().run({'factor_overrides': {**selected(), key: bad}})


def test_legacy_static_required_and_missing_flag_are_unchanged():
    value = tables()
    for field in value['factor_table']:
        field.pop('required_when', None)
    value['factor_table'][0]['required'] = True
    with pytest.raises(ValueError, match='required factor is empty: F011'):
        engine(value).run({})
    assert engine(value).run({'factor_overrides': {'F011': 'A侧'}})['ok']


INVALID_REQUIREMENTS = [
    None,
    {'field': 'missing', 'op': 'eq', 'value': True},
    {'field': 'F012', 'op': 'eq', 'value': True},
    {'field': 'selected_processes', 'op': 'contains', 'value': 'P001'},
    {'some': {'field': 'F010', 'op': 'eq', 'value': True}},
    {'field': 'F010', 'op': 'eq', 'value': None},
    {'field': 'F010', 'op': 'neq', 'value': None},
]


@pytest.mark.parametrize('when', INVALID_REQUIREMENTS)
def test_public_validator_rejects_invalid_or_route_dependent_requirements(when):
    value = tables()
    value['factor_table'][0]['required_when'] = when
    with pytest.raises(DemoTableError):
        validate_demo_tables(value)


@pytest.mark.parametrize('when', INVALID_REQUIREMENTS)
def test_receiver_rejects_invalid_or_route_dependent_requirements(when):
    value = tables()
    value['factor_table'][0]['required_when'] = when
    with pytest.raises(ValueError):
        engine(value)


def test_required_condition_cannot_depend_on_aggregated_cad_values():
    value = tables()
    value['factor_table'][-1].update(source='input_json[].selected', visible=False)
    value['factor_table'][0]['required_when']['field'] = 'F020'
    with pytest.raises(DemoTableError):
        validate_demo_tables(value)
    with pytest.raises(ValueError):
        engine(value)


# Produced by validatedRulePackageDownload.spec.ts through the real TS adapter,
# including its persistent short-ID registry, not a hand-authored three-table pair.
EXPORT = json.loads((Path(__file__).parent / 'fixtures/conditional_required_export.json').read_text(encoding='utf-8'))
SCOPE = 'project_factor.feature_5b54_28_901a_5b54_29'


def test_export_fixture_loads_with_chinese_windows_default_encoding(monkeypatch):
    original = Path.read_text

    def ansi_read_text(path, encoding=None, errors=None):
        return original(path, encoding=encoding or 'cp936', errors=errors)

    monkeypatch.setattr(Path, 'read_text', ansi_read_text)
    runpy.run_path(str(Path(__file__)))


def exported_native(static_required):
    payload = deepcopy(EXPORT['saved']['export_sources']['native_snapshot']['rule_package'])
    payload['manifest'] = {'package_name': 'conditional-export-regression', 'project_id': 35, 'scope': {'key': '35'}}
    for field in payload['input_schema']['fields']:
        if field['key'].startswith(SCOPE + '.') and not field['key'].endswith('.present'):
            field['required'] = static_required
    return RulePackageV2.model_validate(payload)


def exported_inputs(missing=None, bad=None):
    inputs = dict(EXPORT['inputs'][2])
    if missing:
        del inputs[SCOPE + '.' + missing]
    if bad:
        inputs[SCOPE + '.' + bad[0]] = bad[1]
    return inputs


def exported_request(tables, inputs, compact, source_paths):
    inputs = {EXPORT['registry']['factors'][key] if compact else key: value for key, value in inputs.items()}
    groups = {}
    for process in tables['full_route_table']:
        for step in process['steps']:
            for path, names in step['candidates'].items():
                groups.setdefault(path, set()).update(names)
    request = {'input_json': [
        {'group_path': path, 'features': [{'feature_select': name} for name in sorted(names)]}
        for path, names in groups.items()
    ]}
    if not source_paths:
        return dict(request, factor_overrides=inputs)
    fields = {f['key']: f for f in tables['factor_table']}
    for key, value in inputs.items():
        parts = fields[key]['source'].split('.')
        target = request
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = value
    return request


@pytest.mark.parametrize('static_required', [False, True])
@pytest.mark.parametrize('inputs', EXPORT['inputs'])
def test_ts_export_preserves_native_routes_with_original_ids_short_ids_and_source_paths(static_required, inputs):
    package = exported_native(static_required)
    assert not validate_inputs(package.input_schema, inputs)
    normalized, issues = canonicalize_inputs(package.input_schema, inputs)
    assert not issues
    catalog = {p.process_id: p for p in package.route_catalog.processes}
    expected = [catalog[pid].display_name for pid in plan_route(package, normalized).selected_process_ids]
    for compact in (False, True):
        value = EXPORT['compact' if compact else 'tables']
        validate_demo_tables(value)
        for source_paths in (False, True):
            result = engine(value).run(exported_request(value, inputs, compact, source_paths))
            assert [p['process_name'] for p in result['route']] == expected


INVALID_EXPORTED_INPUTS = (
    [exported_inputs(missing=field) for field in ('direction', 'it', 'ra')]
    + [exported_inputs(bad=(field, empty)) for field in ('direction', 'it', 'ra') for empty in (None, '')]
    + [exported_inputs(bad=bad) for bad in (
        ('present', 'true'), ('direction', 1), ('direction', 'B侧'),
        ('it', 6.5), ('it', 4), ('it', 11), ('ra', 0), ('ra', -1),
    )]
    + [{key: value for key, value in exported_inputs().items() if key != 'job.length'}]
)


@pytest.mark.parametrize('static_required', [False, True])
@pytest.mark.parametrize('inputs', INVALID_EXPORTED_INPUTS)
def test_ts_export_rejects_same_missing_or_invalid_selected_inputs_as_native(static_required, inputs):
    assert validate_inputs(exported_native(static_required).input_schema, inputs)
    for compact in (False, True):
        value = EXPORT['compact' if compact else 'tables']
        for source_paths in (False, True):
            with pytest.raises(ValueError):
                engine(value).run(exported_request(value, inputs, compact, source_paths))
