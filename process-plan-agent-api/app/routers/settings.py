from fastapi import APIRouter, HTTPException
from typing import List
from urllib.parse import urlsplit
import httpx

from app.schemas.schemas import SettingOut, SettingUpdate, LLMTestRequest, LLMTestOut, LLMModelOut
from app.services.llm_client import (
    normalize_llm_api_url,
    request_llm_completion,
)
from app.services.settings_store import (
    SettingsStoreError,
    load_settings_for_output,
    serialize_setting_for_output,
    update_setting_value,
    clear_setting_value,
    get_llm_settings_map,
)

router = APIRouter(prefix="/api/settings", tags=["Settings"])


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


@router.post("/test-connection", response_model=LLMTestOut)
async def test_llm_connection(payload: LLMTestRequest):
    """
    测试 LLM API 连接是否正常
    """
    api_url = normalize_llm_api_url(_validated_api_url(payload.api_url))
    api_key = payload.api_key
    model = (payload.model or "").strip()

    if api_key == "__use_saved__":
        try:
            api_key = get_llm_settings_map().get("LLM_API_KEY", "")
        except SettingsStoreError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not api_url or not api_key:
        raise HTTPException(status_code=400, detail="API URL 和 API Key 不能为空")

    try:
        response_text = await request_llm_completion(
            {
                "url": api_url,
                "key": api_key,
                "model": model or ("gpt-4o-mini" if api_url.rstrip("/").endswith("/responses") else "gpt-3.5-turbo"),
            },
            "You are testing an LLM connection. Reply with a short confirmation.",
            "Reply with pong.",
            temperature=0,
            timeout_seconds=30,
            max_tokens=16,
        )
        # A 2xx response without usable text is not a valid model connection.
        # Providers occasionally return an empty stream while still reporting success.
        # Keep this check here so the UI does not claim a false positive.
        if not response_text.strip():
            return LLMTestOut(success=False, message="模型未返回有效内容，请检查模型名称和接口配置。")
        return LLMTestOut(success=True, message="连接成功，模型可用")
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        if status == 401:
            return LLMTestOut(success=False, message="认证失败：API Key 无效或已过期")
        elif status == 403:
            return LLMTestOut(success=False, message="权限不足：请检查 API Key 权限")
        elif status == 404:
            return LLMTestOut(success=False, message="接口地址错误或模型不存在")
        elif status == 429:
            return LLMTestOut(success=False, message="请求过于频繁，请稍后重试")
        elif status in (500, 502, 503, 504):
            return LLMTestOut(success=False, message="模型服务暂时不可用，请稍后重试。")
        else:
            return LLMTestOut(success=False, message=f"模型服务返回 HTTP {status}，请检查接口配置。")
    except httpx.ConnectError:
        return LLMTestOut(success=False, message="无法连接到 API 服务器，请检查网络或地址")
    except httpx.TimeoutException:
        return LLMTestOut(success=False, message="连接超时，请检查网络或稍后重试")
    except httpx.HTTPError:
        return LLMTestOut(success=False, message="无法完成模型请求，请检查网络或接口地址。")
    except (KeyError, TypeError, ValueError):
        return LLMTestOut(success=False, message="模型响应格式无效，请检查接口是否兼容 OpenAI 协议。")
    except Exception:
        return LLMTestOut(success=False, message="测试模型调用失败，请检查配置后重试。")


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

    try:
        configured_url = settings.get("LLM_API_URL", "")
        api_url = normalize_llm_api_url(_validated_api_url(configured_url)) if configured_url else ""
        api_key = settings.get("LLM_API_KEY", "")

        if not api_url or not api_key:
            return []

        # 从 chat/completions 地址推导出 models 地址
        base_url = api_url.rstrip("/")
        if base_url.endswith("/chat/completions"):
            models_url = base_url.replace("/chat/completions", "/models")
        elif base_url.endswith("/responses"):
            models_url = base_url.replace("/responses", "/models")
        elif base_url.endswith("/v1"):
            models_url = f"{base_url}/models"
        else:
            models_url = f"{base_url}/models"

        headers = {
            "Authorization": f"Bearer {api_key}",
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(models_url, headers=headers)
            resp.raise_for_status()
            data = resp.json()

            if not isinstance(data, dict) or not isinstance(data.get("data"), list):
                raise ValueError("expected a data array")
            models = []
            seen = set()
            model_list = data["data"]
            for m in model_list:
                if not isinstance(m, dict) or not isinstance(m.get("id"), str):
                    raise ValueError("expected model objects with string ids")
                model_id = m["id"].strip()
                if model_id and model_id not in seen:
                    models.append(LLMModelOut(id=model_id, name=model_id))
                    seen.add(model_id)

            # 按名称排序
            models.sort(key=lambda x: x.id)
            return models

    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"模型列表获取失败：{exc}") from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="模型列表响应格式无效，请检查接口是否兼容 OpenAI 协议。") from exc
