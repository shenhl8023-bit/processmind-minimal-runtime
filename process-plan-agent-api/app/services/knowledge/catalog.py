"""Deterministic browsing of the same evidence used by knowledge search."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from app.services.knowledge.local_search import (
    CATEGORY_LABELS, ENTITY_ID_FIELDS, _catalog_summary, _flatten,
    _load_records, _record_source, _record_warnings,
)
from app.services.knowledge.guidance_search import guidance_warnings


SECTIONS = {
    'knowledge': ('process_guidance', 'typical_route', 'capability'),
    'resources': ('equipment', 'tool', 'gauge'),
}
TOPICS = {
    'scope': '适用范围', 'rule': '工序安排', 'quality': '质量与检验',
    'fit': '配套与装配', 'reference': '参考说明', 'formula': '计算公式',
    'allowance': '加工余量', 'resource': '工序资源',
    'stage_overview': '阶段概要', 'route': '典型路线',
}
STATUSES = {'verified': '已核对原文', 'pending': '待核对', 'conflict': '存在冲突', 'reference': '参考资料'}


def _text(value: Any) -> str:
    if value is None or value == '' or value == [] or value == {}:
        return '未提供'
    if isinstance(value, list):
        return '、'.join(_text(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _range(fields: Dict[str, Any], low: str, high: str, unit: str) -> str:
    lower, upper = fields.get(low), fields.get(high)
    if lower is None and upper is None:
        return '未提供'
    return '%s～%s %s' % (_text(lower), _text(upper), unit)


def _summary(record: Dict[str, Any]) -> Dict[str, Any]:
    category = record['category']
    fields = record.get('fields') or {}
    guidance = record.get('guidance') or {}
    from_document = category in ('process_guidance', 'typical_route')
    source_kind = 'process_document' if from_document else 'handbook'
    source_label = '规程资料' if from_document else '手册参考'
    status = guidance.get('verification_status', 'reference')
    warnings = _record_warnings(record)
    if not guidance and '待' in str(fields.get('数据状态') or ''):
        status = 'pending'
        warnings.append('源资料标记待确认，请核对原表，不作为确定适配结论。')
    lower, upper = fields.get('主轴转速下限_r_min'), fields.get('主轴转速上限_r_min')
    try:
        if lower is not None and upper is not None and float(lower) > float(upper):
            warnings.append('主轴转速原始下限 %s 大于上限 %s，范围异常；保留原值，请核对来源。' % (lower, upper))
    except (TypeError, ValueError):
        warnings.append('主轴转速原值不能解析为数值，请核对来源。')
    if guidance:
        warnings.extend(guidance_warnings(record))
    title = str(record.get('title') or '未命名记录')
    values = {'title': title, 'source': source_label, 'status': STATUSES.get(status, '待核对')}
    if from_document:
        values.update({
            'type': TOPICS.get(guidance.get('kind'), '工艺说明'),
            'object': _text(guidance.get('part_family') or guidance.get('typical_part')),
            'material': _text(guidance.get('materials')),
            'summary': _text(guidance.get('conditions') or guidance.get('conclusion')),
        })
    elif category == 'capability':
        title = ' · '.join(str(fields[key]) for key in ('加工特征', '加工方法', '加工阶段') if fields.get(key)) or title
        values.update({
            'title': title, 'type': '加工能力参考', 'object': _text(fields.get('加工特征')),
            'material': _text(fields.get('工件材料')),
            'summary': '精度 %s；Ra %s' % (_range(fields, '精度等级下限', '精度等级上限', ''), _range(fields, 'Ra下限_μm', 'Ra上限_μm', 'μm')),
        })
    else:
        values.update({
            'model': _text(fields.get('设备型号') or fields.get('型号或规格') or fields.get('型式')),
            'type': _text(fields.get('设备类别') or fields.get('刀具类别') or fields.get('量具类别')),
        })
        if category == 'equipment':
            values['range'] = '直径 %s mm / 长度 %s mm' % (_text(fields.get('最大工件直径_mm')), _text(fields.get('最大加工长度_mm') if fields.get('最大加工长度_mm') is not None else fields.get('最大工件长度_mm')))
            values['parameter'] = '主轴 %s' % _range(fields, '主轴转速下限_r_min', '主轴转速上限_r_min', 'r/min')
        elif category == 'tool':
            values['range'] = _range(fields, '直径下限_mm', '直径上限_mm', 'mm')
            values['parameter'] = _text(fields.get('适用加工方法'))
        else:
            values['range'] = _range(fields, '测量范围下限_mm', '测量范围上限_mm', 'mm')
            values['parameter'] = _text(fields.get('测量对象'))
    return {
        'id': str(record['id']), 'title': title, 'category': category,
        'source_kind': source_kind, 'source_label': source_label,
        'verification_status': status, 'data_warnings': list(dict.fromkeys(warnings)), 'values': values,
    }


def _guidance_semantic_key(record: Dict[str, Any]) -> str:
    guidance = record.get('guidance') or {}
    source = record.get('source') or {}
    key = {
        'category': record.get('category'),
        'title': str(record.get('title') or '').casefold(),
        'source': {field: source.get(field) for field in (
            'document_id', 'document_name', 'identity', 'page_no', 'worksheet', 'row_no', 'cell_range',
        )},
        'kind': guidance.get('kind'),
        'applicability': guidance.get('applicability'),
        'part_family': guidance.get('part_family'),
        'typical_part': guidance.get('typical_part'),
        'materials': guidance.get('materials'),
        'topics': guidance.get('topics'),
        'conditions': guidance.get('conditions'),
    }
    return json.dumps(key, ensure_ascii=False, sort_keys=True, default=str)


def _guidance_variant_key(record: Dict[str, Any]) -> str:
    guidance = record.get('guidance') or {}
    return json.dumps({
        'conclusion': guidance.get('conclusion'),
        'metrics': guidance.get('metrics'),
    }, ensure_ascii=False, sort_keys=True, default=str)


def _with_guidance_conflicts(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups: Dict[str, List[tuple[int, Dict[str, Any]]]] = {}
    for index, record in enumerate(records):
        if isinstance(record.get('guidance'), dict):
            groups.setdefault(_guidance_semantic_key(record), []).append((index, record))
    conflict_indexes = {
        index
        for members in groups.values()
        if len({_guidance_variant_key(record) for _, record in members}) > 1
        for index, _ in members
    }
    if not conflict_indexes:
        return records
    enriched: List[Dict[str, Any]] = []
    conflict_warning = '同一来源的同一知识项存在不同结论或指标，请核对原文。'
    for index, record in enumerate(records):
        if index not in conflict_indexes:
            enriched.append(record)
            continue
        copy = dict(record)
        guidance = dict(record.get('guidance') or {})
        guidance['verification_status'] = 'conflict'
        copy['guidance'] = guidance
        warnings = list(record.get('data_warnings') or [])
        warnings.append(conflict_warning)
        copy['data_warnings'] = list(dict.fromkeys(warnings))
        enriched.append(copy)
    return enriched


def _entries(section: str) -> List[Dict[str, Any]]:
    records = [record for record in _load_records() if record.get('category') in SECTIONS[section]]
    if section == 'knowledge':
        records = _with_guidance_conflicts(records)
        return [dict(_summary(record), fields=record.get('fields') or {}, sources=[_record_source(record)],
                     guidance=record.get('guidance'), original_records=[record]) for record in records]
    entries = []
    for category in SECTIONS[section]:
        rows = [record for record in records if record['category'] == category]
        id_field = ENTITY_ID_FIELDS[category]
        for group in _catalog_summary(rows, category)[category]:
            # Match all originals by their source identity. Parameter variants remain separate.
            sources = group['sources']
            originals = [row for row in rows if _record_source(row) in sources and
                         all(row.get('fields', {}).get(key) == value for key, value in group['fields'].items())]
            if not originals:
                originals = [row for row in rows if str(row.get('fields', {}).get(id_field)) == str(group['id'])]
            record = originals[0] if originals else rows[0]
            entries.append(dict(_summary(record), fields=record.get('fields') or {}, sources=sources,
                                guidance=None, original_records=originals))
    return entries


def list_catalog(section: str = 'knowledge', category: str = '', topic: str = '', q: str = '',
                 sort: str = 'title_asc', page: int = 1, page_size: int = 20) -> Dict[str, Any]:
    entries = _entries(section)
    categories = [{'value': cat, 'label': CATEGORY_LABELS[cat], 'count': sum(row['category'] == cat for row in entries)}
                  for cat in SECTIONS[section]]
    topic_entries = [row for row in entries if not category or row['category'] == category]
    topics = [{'value': kind, 'label': label, 'count': sum((row.get('guidance') or {}).get('kind') == kind for row in topic_entries)}
              for kind, label in TOPICS.items()] if section == 'knowledge' else []
    terms = q.strip().casefold().split()
    filtered = [row for row in entries
                if (not category or row['category'] == category)
                and (not topic or (row.get('guidance') or {}).get('kind') == topic)
                and all(term in _flatten(row['original_records']).casefold() for term in terms)]
    filtered.sort(key=lambda row: (row['title'].casefold(), row['id']), reverse=sort == 'title_desc')
    raw_count = sum(len(row['original_records']) for row in filtered)
    keys = [('title', '知识条目'), ('type', '主题'), ('object', '适用对象'), ('material', '材料 / 状态'),
            ('summary', '条件 / 指标摘要'), ('status', '核对状态'), ('source', '资料来源')] if section == 'knowledge' else [
            ('title', '资源名称'), ('type', '类别'), ('model', '型号 / 规格'), ('range', '范围 / 尺寸'),
            ('parameter', '主要参数 / 用途'), ('source', '资料来源')]
    visible_keys = ('id', 'title', 'category', 'source_kind', 'source_label', 'verification_status', 'data_warnings', 'values')
    return {
        'section': section, 'total': len(filtered), 'raw_count': raw_count, 'page': page, 'page_size': page_size,
        'categories': categories, 'topics': topics, 'columns': [{'key': key, 'label': label} for key, label in keys],
        'items': [{key: row[key] for key in visible_keys} for row in filtered[(page - 1) * page_size:page * page_size]],
    }


def get_catalog_record(record_id: str) -> Optional[Dict[str, Any]]:
    for section in SECTIONS:
        for entry in _entries(section):
            if entry['id'] == record_id:
                return entry
    return None
