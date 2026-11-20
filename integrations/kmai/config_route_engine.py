#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""三表工艺路线引擎。仅依赖标准库，兼容 Python 3.8。"""
import copy
import fnmatch
import math
import re

MISSING = object()
TYPES = {'bool', 'int', 'number', 'string', 'enum', 'multi_enum'}
OPS = {'eq', 'neq', 'in', 'contains', 'exists', 'gt', 'gte', 'lt', 'lte'}
# FeatureTemplate.xml lists these as hole variants. Keep CAD names in output;
# only candidate matching and factor evaluation use their common family.
HOLE_ALIASES = {'孔(盲孔)': '孔', '孔(通孔)': '孔'}
# The current group template qualifies generic holes by complete path segments.
GROUP_FEATURE_CONTEXT = {
    '中间通孔': '孔(通孔)',
    'A侧/孔': '孔(盲孔)',
    'B侧/孔': '孔(盲孔)',
}
# Internal rows retain CAD context; it never enters the exported factor map.
CAD_FEATURE_CONTEXT = object()

# feat_rank 是每个 CAD 特征的精度等级，数值越小表示精度越高。
PRECISION_INNER_FEATURES = frozenset((
    '孔', '孔(盲孔)', '孔(通孔)', '孔系', '工艺孔', '简单孔',
    '中心孔', '埋头孔', '沉头孔', '阶梯孔', '孔台阶',
    '内圆柱面', '内圆锥面', '内球面', '内螺纹',
))
PRECISION_OUTER_FEATURES = frozenset((
    '圆环面', '外圆柱面', '外圆锥面', '外球面', '外螺纹', '轴台阶', '轴段',
))
PRECISION_FIELD_BUCKETS = (
    ('precision.inner_diameter_it', 'inner'),
    ('precision.dimension_it', 'dimension'),
    ('precision.outer_diameter_it', 'outer'),
)


def merge_dict(base, changes):
    result = copy.deepcopy(base)
    for key, value in changes.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_dict(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def normalize_request(request):
    if not isinstance(request, dict):
        raise ValueError('request must be an object')
    root = copy.deepcopy(request.get('input_payload') or request.get('payload') or {})
    if not isinstance(root, dict):
        root = {}
    root = merge_dict(root, {k: v for k, v in request.items() if k not in ('input_payload', 'payload')})
    if 'input_json' not in root:
        root['input_json'] = root.get('cad_input', root.get('cad_features', []))
    if not isinstance(root['input_json'], list):
        raise ValueError('input_json must be an array')
    defaults = root.get('manual_defaults', {})
    manual = root.get('manual', {})
    if not isinstance(defaults, dict) or not isinstance(manual, dict):
        raise ValueError('manual_defaults/manual must be objects')
    root['manual_defaults'] = merge_dict(defaults, {k: v for k, v in manual.items() if k != 'factor_overrides'})
    overrides = manual.get('factor_overrides', {})
    if not isinstance(overrides, dict) or not isinstance(root.get('factor_overrides', {}), dict):
        raise ValueError('factor_overrides must be an object')
    root['factor_overrides'] = merge_dict(overrides, root.get('factor_overrides', {}))
    infer_precision_defaults(root)
    return root


def tokens(source):
    if not isinstance(source, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*(\[\])?(\.[A-Za-z_][A-Za-z0-9_]*(\[\])?)*', source):
        raise ValueError('invalid source: %s' % source)
    return [(part.replace('[]', ''), part.endswith('[]')) for part in source.split('.')]


def read_source(root, parts, indices=None, prefix=''):
    if not parts:
        return root
    key, many = parts[0]
    if not isinstance(root, dict) or key not in root:
        return MISSING
    value = root[key]
    path = prefix + key
    if many:
        if not isinstance(value, list):
            raise ValueError('%s must be an array' % path)
        path += '[]'
        if indices is not None and path in indices:
            idx = indices[path]
            if idx >= len(value):
                return MISSING
            return read_source(value[idx], parts[1:], indices, path + '.')
        result = []
        for item in value:
            found = read_source(item, parts[1:], indices, path + '.')
            if found is MISSING:
                continue
            if any(p[1] for p in parts[1:]) and isinstance(found, list):
                result.extend(found)
            else:
                result.append(found)
        return result
    return read_source(value, parts[1:], indices, path + '.')


def write_manual(root, source, value):
    if not source.startswith('manual_defaults.') or '[]' in source:
        return
    target = root['manual_defaults']
    parts = source.split('.')[1:]
    for part in parts[:-1]:
        if not isinstance(target.get(part), dict):
            target[part] = {}
        target = target[part]
    target[parts[-1]] = copy.deepcopy(value)


def empty(value):
    return value is MISSING or value is None or value == '' or value == []


def _supported_precision_rank(value):
    """将可直接填入 IT 输入框的特征精度等级规范为整数。"""
    if type(value) not in (int, float):
        return None
    try:
        if not math.isfinite(value) or int(value) != value or value < 5 or value > 10:
            return None
    except (OverflowError, ValueError):
        return None
    return int(value)


def _precision_bucket(feature_name):
    name = str(feature_name or '').strip()
    if name in PRECISION_INNER_FEATURES:
        return 'inner'
    if name in PRECISION_OUTER_FEATURES:
        return 'outer'
    return 'dimension'


def infer_precision_defaults(root):
    """从当前 CAD 输入的 feat_rank 补齐未提供的精度参数。"""
    manual_defaults = root.get('manual_defaults')
    if not isinstance(manual_defaults, dict):
        return root

    precision = manual_defaults.get('precision')
    if precision is None:
        precision = {}
        manual_defaults['precision'] = precision
    elif not isinstance(precision, dict):
        return root

    ranks = {'inner': [], 'dimension': [], 'outer': []}
    for block in root.get('input_json', []):
        if not isinstance(block, dict):
            continue
        for feature in block.get('features', []):
            if not isinstance(feature, dict):
                continue
            rank = _supported_precision_rank(feature.get('feat_rank'))
            if rank is None:
                continue
            ranks[_precision_bucket(feature.get('feature_select'))].append(rank)

    overrides = root.get('factor_overrides', {})
    if not isinstance(overrides, dict):
        overrides = {}
    for field, bucket in PRECISION_FIELD_BUCKETS:
        if field in overrides:
            continue
        if not empty(precision.get(field.rsplit('.', 1)[-1], MISSING)):
            continue
        values = ranks[bucket]
        if values:
            precision[field.rsplit('.', 1)[-1]] = min(values)
    return root


def finite_number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def validate_factor_limits(factor):
    limits = factor.get('validation', {})
    numeric = factor['type'] in ('int', 'number')
    allowed = {'min', 'max'} if numeric else (
        {'min_length', 'max_length'} if factor['type'] in ('string', 'enum', 'multi_enum') else set())
    if not isinstance(limits, dict) or set(limits) - allowed:
        raise ValueError('invalid validation for factor %s' % factor['key'])
    for name, value in limits.items():
        valid = finite_number(value) if numeric else type(value) is int and value >= 0
        if not valid:
            raise ValueError('invalid validation.%s for factor %s' % (name, factor['key']))
    lower, upper = ('min', 'max') if numeric else ('min_length', 'max_length')
    if lower in limits and upper in limits and limits[lower] > limits[upper]:
        raise ValueError('invalid validation range for factor %s' % factor['key'])


def normalized_path(value):
    return str(value).replace('\\', '/').strip('/')


def matches_feature_candidate(expected, actual, group_path):
    if actual == expected or (expected == '孔' and HOLE_ALIASES.get(actual) == expected):
        return True
    if actual != '孔':
        return False
    path = '/' + normalized_path(group_path) + '/'
    meanings = {kind for group, kind in GROUP_FEATURE_CONTEXT.items()
                if '/' + group + '/' in path}
    # Conflicting group meanings cannot establish a subtype.
    return len(meanings) == 1 and expected in meanings


class ConfigRouteEngine:
    def __init__(self, factor_table, full_route_table, rule_table):
        if not all(isinstance(x, list) for x in (factor_table, full_route_table, rule_table)):
            raise ValueError('three tables must be arrays')
        self.factor_table = copy.deepcopy(factor_table)
        self.catalog = copy.deepcopy(full_route_table)
        self.factors = {}
        self.sources = {}
        for f in self.factor_table:
            if not isinstance(f, dict) or not all(k in f for k in ('key', 'label', 'type', 'source', 'visible')):
                raise ValueError('factor requires key/label/type/source/visible')
            key = f['key']
            if not isinstance(key, str) or not key or key == 'selected_processes' or key in self.factors:
                raise ValueError('duplicate or reserved factor: %s' % key)
            if f['type'] not in TYPES or type(f['visible']) is not bool or type(f.get('required', False)) is not bool:
                raise ValueError('invalid factor type/visible/required: %s' % key)
            self.sources[key] = tokens(f['source'])
            if f['visible'] and '[]' in f['source']:
                raise ValueError('visible factor must be scalar source: %s' % key)
            if 'options' in f:
                options = f['options']
                if f['type'] not in ('enum', 'multi_enum') or not isinstance(options, list) or not all(isinstance(x, str) for x in options) or len(set(options)) != len(options):
                    raise ValueError('invalid options: %s' % key)
            validate_factor_limits(f)
            self.factors[key] = f
            if 'default' in f:
                self.value(f, f['default'])
        self.processes = {}
        self.nodes = {}
        self.parent = {}
        for p in self.catalog:
            if not isinstance(p, dict) or not all(k in p for k in ('process_id', 'process_name', 'process_type', 'precision', 'steps')):
                raise ValueError('process requires id/name/type/precision/steps')
            self.add_node(p['process_id'], p)
            self.processes[p['process_id']] = p
            if not isinstance(p['steps'], list) or p['process_type'] not in ('加工工序', '辅助工序'):
                raise ValueError('invalid process steps/type: %s' % p['process_id'])
            for s in p['steps']:
                if not isinstance(s, dict) or not all(k in s for k in ('step_id', 'step_name', 'candidates')):
                    raise ValueError('step requires id/name/candidates')
                self.add_node(s['step_id'], s)
                self.parent[s['step_id']] = p['process_id']
                if not isinstance(s['candidates'], dict) or not all(isinstance(k, str) and isinstance(v, list) and all(isinstance(x, str) for x in v) for k, v in s['candidates'].items()):
                    raise ValueError('invalid candidates: %s' % s['step_id'])
        self.rules = {}
        self.dependencies = {key: set() for key in self.processes}
        for rule in rule_table:
            if not isinstance(rule, dict):
                raise ValueError('rule must be an object')
            target = rule.get('target')
            if target not in self.nodes:
                raise ValueError('unknown target: %s' % target)
            if target in self.rules:
                raise ValueError('duplicate rule: %s' % target)
            if type(rule.get('required', False)) is not bool or ('when' not in rule and not rule.get('required')):
                raise ValueError('rule requires when or required=true: %s' % target)
            self.rules[target] = rule
            if 'when' in rule:
                deps = self.validate_condition(rule['when'])
                self.dependencies[self.parent.get(target, target)].update(deps)
            if 'feature_filter' in rule:
                deps = self.validate_condition(rule['feature_filter'])
                self.dependencies[self.parent.get(target, target)].update(deps)
        visited, active = set(), set()

        def visit(pid):
            if pid in active:
                raise ValueError('dependency cycle: %s' % pid)
            if pid in visited:
                return
            active.add(pid)
            for dep in self.dependencies[pid]:
                visit(dep)
            active.remove(pid)
            visited.add(pid)
        for pid in self.processes:
            visit(pid)
        for f in self.factor_table:
            if 'required_when' in f:
                self.validate_required_when(f['required_when'])

    def validate_required_when(self, condition):
        """Input requirements use typed scalar factors, independent of routes/CAD rows."""
        self.validate_condition(condition)
        if type(condition) is bool:
            return
        for branch in ('all', 'any', 'not'):
            if branch in condition:
                children = [condition[branch]] if branch == 'not' else condition[branch]
                for child in children:
                    self.validate_required_when(child)
                return
        if 'some' in condition or condition.get('field') == 'selected_processes':
            raise ValueError('required_when cannot depend on route results or CAD rows')
        field, op, value = condition['field'], condition['op'], condition['value']
        f = self.factors[field]
        if '[]' in f['source']:
            raise ValueError('required_when cannot depend on aggregated CAD factors: %s' % field)
        kind = f['type']

        def scalar(item):
            if kind == 'bool':
                return type(item) is bool
            if kind == 'int':
                return type(item) is int
            if kind == 'number':
                return finite_number(item)
            return isinstance(item, str)

        valid = (type(value) is bool if op == 'exists' else
                 kind in ('int', 'number') and finite_number(value) if op in ('gt', 'gte', 'lt', 'lte') else
                 kind != 'multi_enum' and isinstance(value, list) and all(scalar(item) for item in value) if op == 'in' else
                 kind in ('string', 'enum', 'multi_enum') and isinstance(value, str) if op == 'contains' else
                 op in ('eq', 'neq') and scalar(value))
        if not valid:
            raise ValueError('required_when condition value has wrong type: %s' % field)

    def add_node(self, key, node):
        if not isinstance(key, str) or not key or key in self.nodes:
            raise ValueError('duplicate or invalid node: %s' % key)
        self.nodes[key] = node

    def validate_condition(self, c):
        if type(c) is bool:
            return set()
        if not isinstance(c, dict):
            raise ValueError('condition must be boolean or object')
        for op in ('all', 'any', 'not', 'some'):
            if op in c:
                if len(c) != 1:
                    raise ValueError('condition has extra keys: %s' % op)
                if op in ('all', 'any'):
                    if not isinstance(c[op], list) or not c[op]:
                        raise ValueError('%s requires nonempty array' % op)
                    return set().union(*(self.validate_condition(x) for x in c[op]))
                return self.validate_condition(c[op])
        if set(c) != {'field', 'op', 'value'}:
            raise ValueError('condition requires field/op/value')
        field, op, value = c['field'], c['op'], c['value']
        if op not in OPS:
            raise ValueError('invalid operator: %s' % op)
        if field == 'selected_processes':
            if op != 'contains' or not isinstance(value, str) or value not in self.processes:
                raise ValueError('unknown/invalid selected_processes dependency: %s' % value)
            return {value}
        if field not in self.factors:
            raise ValueError('unknown factor: %s' % field)
        if op == 'in' and not isinstance(value, list):
            raise ValueError('in requires array: %s' % field)
        if op == 'exists' and type(value) is not bool:
            raise ValueError('exists requires boolean: %s' % field)
        if op in ('gt', 'gte', 'lt', 'lte'):
            if self.factors[field]['type'] not in ('int', 'number') or type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError('numeric comparison requires number: %s' % field)
        return set()

    def value(self, f, raw, validate_limits=True):
        kind, key = f['type'], f['key']
        if isinstance(raw, str):
            if f['source'] == 'input_json[].features[].feature_select':
                raw = HOLE_ALIASES.get(raw, raw)
            elif f['source'] == 'input_json[].group_path':
                raw = normalized_path(raw)
        if raw is MISSING:
            raw = copy.deepcopy(f.get('default', {'bool': False, 'multi_enum': [], 'int': None, 'number': None}.get(kind, '')))
        if raw is None:
            return None
        valid = ((kind == 'bool' and type(raw) is bool) or
                 (kind == 'int' and type(raw) is int) or
                 (kind == 'number' and finite_number(raw)) or
                 (kind in ('string', 'enum') and isinstance(raw, str)) or
                 (kind == 'multi_enum' and isinstance(raw, list) and all(isinstance(x, str) for x in raw)))
        if not valid:
            raise ValueError('invalid %s value for factor %s' % (kind, key))
        if kind in ('enum', 'multi_enum') and 'options' in f:
            values = raw if kind == 'multi_enum' else ([raw] if raw else [])
            if any(x not in f['options'] for x in values):
                raise ValueError('unknown option for factor %s: %s' % (key, raw))
        if validate_limits and not empty(raw):
            limits = f.get('validation', {})
            measured = raw if kind in ('int', 'number') else len(raw) if kind in ('string', 'enum', 'multi_enum') else None
            lower, upper = ('min', 'max') if kind in ('int', 'number') else ('min_length', 'max_length')
            if lower in limits and measured < limits[lower]:
                raise ValueError('%s (%s) 不能小于 %s%s' % (f['label'], key, limits[lower], '' if lower == 'min' else '（长度/数量）'))
            if upper in limits and measured > limits[upper]:
                raise ValueError('%s (%s) 不能大于 %s%s' % (f['label'], key, limits[upper], '' if upper == 'max' else '（长度/数量）'))
        return copy.deepcopy(raw)

    def map_factors(self, root, parameters):
        overrides = root['factor_overrides']
        for key in overrides:
            if key not in self.factors or not self.factors[key]['visible']:
                raise ValueError('unknown or hidden factor override: %s' % key)
        factors = {}
        for key, f in self.factors.items():
            if key == 'cad.features':
                # CAD 特征选项由因素表管理，运行时固定选择全部配置项。
                raw = copy.deepcopy(f.get('options', []))
                if key in overrides:
                    overrides[key] = copy.deepcopy(raw)
            else:
                raw = overrides[key] if key in overrides else read_source(root, self.sources[key])
            if '[]' in f['source']:
                factors[key] = [self.value(f, v, validate_limits=not parameters) for v in ([] if raw is MISSING else raw)]
            else:
                factors[key] = self.value(f, raw, validate_limits=not parameters)
                write_manual(root, f['source'], factors[key])
        rows, feature_rows = [], {}
        for i, block in enumerate(root['input_json']):
            if not isinstance(block, dict) or not isinstance(block.get('features', []), list):
                raise ValueError('invalid CAD group at index %s' % i)
            for j, feature in enumerate(block.get('features', []) or [{}]):
                if not isinstance(feature, dict):
                    raise ValueError('invalid CAD feature at index %s/%s' % (i, j))
                indices = {'input_json[]': i, 'input_json[].features[]': j}
                row = dict(factors)
                for key, f in self.factors.items():
                    if '[]' in f['source']:
                        row[key] = self.value(f, read_source(root, self.sources[key], indices), validate_limits=not parameters)
                row[CAD_FEATURE_CONTEXT] = (
                    normalized_path(block.get('group_path', '')),
                    feature.get('feature_select', MISSING))
                rows.append(row)
                if j < len(block.get('features', [])):
                    feature_rows[(i, j)] = row
        if not parameters:
            # Requirements may reference later factors: map all inputs first.
            for key, f in self.factors.items():
                required = f.get('required', False) or (
                    'required_when' in f and self.condition(f['required_when'], factors, rows, set()))
                if required and empty(factors[key]):
                    raise ValueError('required factor is empty: %s (%s)' % (key, f['label']))
        return factors, rows, feature_rows

    def condition(self, c, factors, rows, selected):
        if type(c) is bool:
            return c
        if 'all' in c:
            return all(self.condition(x, factors, rows, selected) for x in c['all'])
        if 'any' in c:
            return any(self.condition(x, factors, rows, selected) for x in c['any'])
        if 'not' in c:
            return not self.condition(c['not'], factors, rows, selected)
        if 'some' in c:
            return any(self.condition(c['some'], row, [row], selected) for row in rows)
        field, op, wanted = c['field'], c['op'], c['value']
        actual = selected if field == 'selected_processes' else factors.get(field)
        if op == 'exists':
            return (not empty(actual)) == wanted
        if op == 'contains':
            return isinstance(actual, (str, list, set)) and wanted in actual
        if op == 'neq':
            return not self.condition(dict(field=field, op='eq', value=wanted), factors, rows, selected)
        if (op in ('eq', 'in') and self.factors[field]['type'] in ('string', 'enum')
                and self.factors[field]['source'] == 'input_json[].features[].feature_select'):
            names = wanted if op == 'in' else [wanted]
            for row in rows:
                path, original = row[CAD_FEATURE_CONTEXT]
                # Aggregate sources omit missing values; only explicit row
                # conditions (some/feature_filter) apply per-feature defaults.
                if original is MISSING and CAD_FEATURE_CONTEXT not in factors:
                    continue
                value = row[field] if original is MISSING else original
                if isinstance(value, str) and any(
                        isinstance(name, str) and matches_feature_candidate(name, value, path)
                        for name in names):
                    return True
            return False
        values = actual if isinstance(actual, list) else [actual]
        for value in values:
            if value is None:
                continue
            if op == 'eq' and type(value) is type(wanted) and value == wanted:
                return True
            if op == 'in' and value in wanted:
                return True
            if op in ('gt', 'gte', 'lt', 'lte') and type(value) in (int, float):
                if {'gt': value > wanted, 'gte': value >= wanted, 'lt': value < wanted, 'lte': value <= wanted}[op]:
                    return True
        return False

    def bind_candidates(self, template, cad, allowed=None):
        bound = {}
        for i, block in enumerate(cad):
            path = normalized_path(block.get('group_path', ''))
            for pattern, names in template.items():
                if not fnmatch.fnmatchcase(path, normalized_path(pattern)):
                    continue
                # 模板顺序保持稳定；输出路径始终取自实际 CAD 数据。
                actual = [f.get('feature_select') for j, f in enumerate(block.get('features', []))
                          if allowed is None or (i, j) in allowed]
                matches = [actual_name for name in names for actual_name in actual
                           if isinstance(actual_name, str) and
                           matches_feature_candidate(name, actual_name, path)]
                if matches:
                    bound.setdefault(path, [])
                    bound[path].extend(x for x in matches if x not in bound[path])
        return bound

    def run(self, request, parameters=False):
        root = normalize_request(request)
        factors, rows, feature_rows = self.map_factors(root, parameters)
        result = {'ok': True, 'status': 'success', 'factors': factors,
                  'manual': copy.deepcopy(root['manual_defaults']), 'normalized_input': root}
        if parameters:
            result['factor_table'] = copy.deepcopy(self.factor_table)
            return result
        selected, evaluated, output = set(), set(), {}

        def enabled(target, default=False):
            rule = self.rules.get(target)
            return default if rule is None else (rule.get('required', False) or self.condition(rule.get('when', False), factors, rows, selected))

        def choose(pid):
            if pid in evaluated:
                return
            for dep in self.dependencies[pid]:
                choose(dep)
            evaluated.add(pid)
            if not enabled(pid):
                return
            p = self.processes[pid]
            steps = []
            for s in p['steps']:
                if not enabled(s['step_id'], True):
                    continue
                # A step may override its process filter, e.g. drilling during
                # a milling setup. No implicit inference from activation rules.
                feature_filter = self.rules.get(s['step_id'], {}).get(
                    'feature_filter', self.rules.get(pid, {}).get('feature_filter'))
                allowed = None if feature_filter is None else {
                    identity for identity, row in feature_rows.items()
                    if self.condition(feature_filter, row, [row], selected)}
                candidates = self.bind_candidates(s['candidates'], root['input_json'], allowed)
                if s['candidates'] and not candidates:
                    continue
                steps.append({'step_name': s['step_name'], 'candidates': candidates, 'is_last': False})
            if p['steps'] and not steps and not self.rules.get(pid, {}).get('required', False):
                return
            selected.add(pid)
            output[pid] = {'process_name': p['process_name'], 'process_type': p['process_type'],
                           'precision': p['precision'], 'technical_requirements': [], 'steps': steps}
        for pid in self.processes:
            choose(pid)
        route = [output[p['process_id']] for p in self.catalog if p['process_id'] in output]
        last = {}
        for pi, p in enumerate(route):
            for si, s in enumerate(p['steps']):
                for path, names in s['candidates'].items():
                    for name in names:
                        last[(path, name)] = (pi, si)
        matched = []
        for pi, p in enumerate(route):
            internal_steps = []
            for si, s in enumerate(p['steps']):
                details = []
                for path, names in s['candidates'].items():
                    flags = [{'feature_name': n, 'is_last_process_for_feature': last[(path, n)] == (pi, si)} for n in names]
                    last_names = [x['feature_name'] for x in flags if x['is_last_process_for_feature']]
                    details.append({'group_path': path, 'group_name': path.split('/')[-1], 'features': names,
                                    'is_last_process_for_group': bool(last_names), 'last_features': last_names, 'feature_flags': flags})
                s['candidate_details'] = details
                s['is_last'] = any(d['last_features'] for d in details)
                internal_steps.append({'工步名': s['step_name'], '候选分组': s['candidates'], '候选明细': details})
            matched.append({'序号': pi, '工序名': p['process_name'], '工序类型': p['process_type'],
                            '加工精度': p['precision'], '技术要求': [], '工步': internal_steps})
        result.update(route=route, standard_route={'工艺路线': copy.deepcopy(matched)},
                      matched_route={'schema_version': '2.0', '工艺路线': matched},
                      summary={'group_block_count': len(root['input_json']),
                               'feature_count': sum(len(b.get('features', [])) for b in root['input_json']),
                               'process_count': len(route), 'step_count': sum(len(p['steps']) for p in route),
                               'true_factor_keys': [k for k, v in factors.items() if v is True]})
        return result
