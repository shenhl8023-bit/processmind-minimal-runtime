"""Bounded model work for a guide; no database writes or partial publication."""
import asyncio
from copy import deepcopy
import json
import logging
import time

from fastapi import HTTPException

from app.services.llm_service import parse_json_from_llm

logger = logging.getLogger(__name__)
BATCH_SIZE = 16
MAX_CONCURRENCY = 3
DOMAIN_KEYS = ('feature_mappings', 'directions', 'materials', 'guidance')


def _invalid(reason):
    raise HTTPException(422, {'code': 'analysis_questions_invalid',
        'message': '问答生成未完成，请重试。', 'reason': reason})


def _reference(configuration, names, operation_reference):
    """Fixed question trees/options are local; send relevant reviewed choices."""
    result = {key: deepcopy(configuration[key]) for key in DOMAIN_KEYS}
    result['operation_guidance'] = {}
    for name in names:
        operation = operation_reference(configuration, name)
        if operation:
            result['operation_guidance'][name] = {key: deepcopy(value)
                for key, value in operation.items()
                if key in ('feature_group', 'recommendation', 'instruction')}
    return result


def _merge(outputs, names):
    result = {'operation_guidance': {}}
    for output, batch_names in outputs:
        if not isinstance(output, dict) or not isinstance(output.get('operation_guidance'), dict):
            _invalid('缺少工序问题')
        if set(output) - set(DOMAIN_KEYS) - {'operation_guidance'}:
            _invalid('包含不支持的生成字段')
        if set(output['operation_guidance']) - set(batch_names):
            _invalid('工序不属于当前生成批次')
        result['operation_guidance'].update(output['operation_guidance'])
        for key in DOMAIN_KEYS:
            if key not in output:
                continue
            if key == 'feature_mappings':
                if not isinstance(output[key], dict):
                    _invalid('特征候选不是映射')
                target = result.setdefault(key, {})
                for group, choices in output[key].items():
                    if group in target and target[group] != choices:
                        _invalid('分批生成的特征候选冲突，请核对指导文件：%s' % group)
                    target[group] = choices
            else:
                if key in result and result[key] != output[key]:
                    _invalid('分批生成的%s候选或指导冲突，请核对指导文件' % key)
                result[key] = output[key]
    return result


async def generate_batches(*, call_model, prompt, model_config, names, route_context,
                           reference, default_complete, validate, operation_reference,
                           retry_names=()):
    targets = list(retry_names or names)
    context = dict(zip(names, route_context))
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

    async def request(batch, configuration, errors=None):
        payload = {'operation_names': batch, 'route_operation_names': names,
            'route': [context[name] for name in batch],
            'reference_configuration': _reference(configuration, batch, operation_reference)}
        if errors:
            payload['repair_errors'] = {name: errors[name] for name in batch}
        user = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
        async with semaphore:
            started = time.monotonic()
            output = await call_model(prompt, user, config=model_config,
                max_tokens=min(6000, 500 + 320 * len(batch)), timeout_seconds=50, max_retries=2)
            logger.info('Analysis model batch nodes=%s input_chars=%s output_chars=%s elapsed=%.2fs repair=%s',
                len(batch), len(prompt) + len(user), len(output or ''), time.monotonic() - started, bool(errors))
        if not output:
            raise HTTPException(503, {'code': 'analysis_generation_unavailable',
                'message': '问答生成未完成，请检查模型配置后重试。'})
        raw = parse_json_from_llm(output)
        # A malformed batch can be repaired once, without regenerating siblings.
        if not isinstance(raw, dict) or not isinstance(raw.get('operation_guidance'), dict):
            if errors:
                _invalid('缺少工序问题')
            raw = {'operation_guidance': {name: None for name in batch}}
        return raw, batch

    async def requests(wanted, configuration, errors=None):
        tasks = [asyncio.create_task(request(wanted[i:i + BATCH_SIZE], configuration, errors))
                 for i in range(0, len(wanted), BATCH_SIZE)]
        try:
            return await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    raw = _merge(await requests(targets, reference), targets)
    if retry_names:
        # Published wording/domains stay frozen. Only absent recommendations change.
        operations = deepcopy(reference['operation_guidance'])
        for name in targets:
            proposal = raw['operation_guidance'].get(name)
            if isinstance(proposal, dict):
                operations[name]['recommendation'] = proposal.get('recommendation')
        return validate({'operation_guidance': operations}, reference, names, default_complete)

    # Validate global domains independently so malformed domains are not confused
    # with a single bad operation. Relations always see the full ordered route.
    domains = validate(dict(raw, operation_guidance={}), reference, names,
                       default_complete, target_names=[])
    errors = {}
    for name in targets:
        try:
            operation = raw['operation_guidance'].get(name)
            if name in raw['operation_guidance'] and operation is None:
                _invalid('工序问题格式错误')
            validate(dict(raw, operation_guidance=({name: operation} if operation is not None else {})),
                     reference, names, default_complete, target_names=[name])
        except HTTPException as exc:
            if exc.status_code != 422:
                raise
            errors[name] = str(exc.detail.get('reason', '工序问题格式错误'))[:600]
    if errors:
        repairs = _merge(await requests(list(errors), domains, errors), list(errors))
        # Repair cannot silently rewrite candidates used by already valid nodes.
        for key in DOMAIN_KEYS:
            if key not in repairs:
                continue
            if key == 'feature_mappings':
                if any(domains[key].get(group) != choices for group, choices in repairs[key].items()):
                    _invalid('补生成不得更改已校验的特征候选')
            elif repairs[key] != domains[key]:
                _invalid('补生成不得更改已校验的候选和指导')
        for name in errors:
            if name not in repairs['operation_guidance']:
                _invalid('补生成遗漏当前路线工序：%s' % name)
            raw['operation_guidance'][name] = repairs['operation_guidance'][name]
    return validate(raw, reference, names, default_complete)
