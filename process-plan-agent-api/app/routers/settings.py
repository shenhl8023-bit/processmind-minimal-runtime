import asyncio
from fastapi import APIRouter, HTTPException
from typing import List
from urllib.parse import urlsplit
import httpx

from app.schemas.schemas import SettingOut, SettingUpdate, LLMTestRequest, LLMTestOut, LLMModelOut, LLMSettingsUpdate
from app.services.llm_client import (
    normalize_llm_api_url,
    request_llm_completion,
)
from app.services.llm_errors import describe_llm_error
from app.services.settings_store import (
    SettingsStoreError,
    load_settings_for_output,
    serialize_setting_for_output,
    update_setting_value,
    update_llm_settings,
    clear_setting_value,
    get_llm_settings_map,
)

router = APIRouter(prefix="/api/settings", tags=["Settings"])
LLM_TEST_TIMEOUT_SECONDS = 20.0
LLM_MODELS_TIMEOUT_SECONDS = 15.0


def _validated_api_url(value: str) -> str:
    value = value.strip()
    try:
        parsed = urlsplit(value)
        _ = parsed.port
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value)
        ):
            raise ValueError("invalid HTTP URL")
    except ValueError as exc:
        raise HTTPException(400, "API 地址必须是有效的 HTTP 或 HTTPS URL") from exc
    return value


@router.get("", response_model=List[SettingOut])
async def get_settings():
    """
    获取所有系统设置
    """
    try:
        return load_settings_for_output()
    except SettingsStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("", response_model=SettingOut)
async def update_setting(payload: SettingUpdate):
    """
    更新系统设置
    """
    if payload.key in {"LLM_API_URL", "KNOWLEDGE_SEARCH_API_URL"}:
        payload.value = _validated_api_url(payload.value)
    try:
        updated = update_setting_value(payload.key, payload.value)
        return serialize_setting_for_output(updated)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Setting {payload.key} not found")
    except SettingsStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post('/llm', response_model=List[SettingOut])
async def save_llm_settings(payload: LLMSettingsUpdate):
    api_url = _validated_api_url(payload.api_url)
    try:
        saved = update_llm_settings(api_url, payload.model, payload.api_key)
        return [serialize_setting_for_output(row) for row in saved]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SettingsStoreError as exc:
        raise HTTPException(status_code=500, detail='模型配置保存失败，原有配置未更改，请重试。') from exc


def _resolve_api_key(value: str) -> str:
    value = value.strip()
    if value == '__use_saved__':
        try:
            return get_llm_settings_map().get('LLM_API_KEY', '').strip()
        except SettingsStoreError as exc:
            raise HTTPException(status_code=500, detail='无法读取已保存的模型配置，请检查设置文件。') from exc
    return value


@router.post("/test-connection", response_model=LLMTestOut, response_model_exclude_none=True)
async def test_llm_connection(payload: LLMTestRequest):
    """
    测试 LLM API 连接是否正常
    """
    api_url = normalize_llm_api_url(_validated_api_url(payload.api_url))
    api_key = _resolve_api_key(payload.api_key)
    model = (payload.model or "").strip()

    if not api_url or not api_key:
        raise HTTPException(status_code=400, detail="API URL 和 API Key 不能为空")

    try:
        response_text = await asyncio.wait_for(request_llm_completion(
            {
                "url": api_url,
                "key": api_key,
                "model": model or ("gpt-4o-mini" if api_url.rstrip("/").endswith("/responses") else "gpt-3.5-turbo"),
            },
            "You are testing an LLM connection. Reply with a short confirmation.",
            "Reply with pong.",
            temperature=0,
            timeout_seconds=LLM_TEST_TIMEOUT_SECONDS,
            max_retries=0,
            max_tokens=64,
        ), timeout=LLM_TEST_TIMEOUT_SECONDS)
        # A 2xx response without usable text is not a valid model connection.
        # Providers occasionally return an empty stream while still reporting success.
        # Keep this check here so the UI does not claim a false positive.
        if not response_text.strip():
            return LLMTestOut(success=False, code='llm_response_invalid', message="模型未返回有效内容，请检查模型名称和接口配置。")
        return LLMTestOut(success=True, message="连接成功，模型可用")
    except Exception as exc:
        code, message = describe_llm_error(exc)
        return LLMTestOut(success=False, code=code, message=message)


@router.delete("/{key}", response_model=SettingOut)
async def clear_setting(key: str):
    """Explicitly clear a setting; used for secret values such as API keys."""
    if key not in {"LLM_API_KEY", "KNOWLEDGE_SEARCH_API_KEY"}:
        raise HTTPException(status_code=400, detail="只有密钥设置支持清空操作")
    try:
        return serialize_setting_for_output(clear_setting_value(key))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Setting {key} not found")
    except SettingsStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/models", response_model=List[LLMModelOut])
async def get_available_models():
    """
    获取当前 API 支持的模型列表
    """
    try:
        settings = get_llm_settings_map()
    except SettingsStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    configured_url = settings.get("LLM_API_URL", "")
    if not configured_url or not settings.get('LLM_API_KEY', '').strip():
        return []
    api_url = normalize_llm_api_url(_validated_api_url(configured_url))
    return await _models_for_config(api_url, settings['LLM_API_KEY'].strip(), legacy_errors=True)


@router.post('/models', response_model=List[LLMModelOut])
async def get_draft_models(payload: LLMTestRequest):
    api_url = normalize_llm_api_url(_validated_api_url(payload.api_url))
    api_key = _resolve_api_key(payload.api_key)
    if not api_key:
        raise HTTPException(status_code=400, detail='请输入 API Key')
    return await _models_for_config(api_url, api_key)


async def _models_for_config(api_url: str, api_key: str, legacy_errors: bool = False):
    try:
        return await asyncio.wait_for(_fetch_models(api_url, api_key), timeout=LLM_MODELS_TIMEOUT_SECONDS)
    except Exception as exc:
        code, message = describe_llm_error(exc)
        detail = message if legacy_errors else {'code': code, 'message': message}
        raise HTTPException(status_code=502, detail=detail) from exc


async def _fetch_models(api_url: str, api_key: str):
    endpoint_suffix = '/responses' if api_url.endswith('/responses') else '/chat/completions'
    models_url = api_url[:-len(endpoint_suffix)] + '/models'
    async with httpx.AsyncClient(timeout=LLM_MODELS_TIMEOUT_SECONDS) as client:
        resp = await client.get(models_url, headers={'Authorization': 'Bearer ' + api_key})
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict) or not isinstance(data.get('data'), list):
            raise ValueError('expected a data array')
        models = []
        seen = set()
        for item in data['data']:
            if not isinstance(item, dict) or not isinstance(item.get('id'), str):
                raise ValueError('expected model objects with string ids')
            model_id = item['id'].strip()
            if model_id and model_id not in seen:
                models.append(LLMModelOut(id=model_id, name=model_id))
                seen.add(model_id)
        return sorted(models, key=lambda item: item.id)
