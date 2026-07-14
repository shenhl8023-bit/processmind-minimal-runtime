from fastapi import APIRouter, HTTPException
from typing import List
import httpx

from app.schemas.schemas import SettingOut, SettingUpdate, LLMTestRequest, LLMTestOut, LLMModelOut
from app.services.llm_client import normalize_llm_api_url
from app.services.settings_store import (
    load_settings_for_output,
    serialize_setting_for_output,
    update_setting_value,
    get_llm_settings_map,
)

router = APIRouter(prefix="/api/settings", tags=["Settings"])


@router.get("", response_model=List[SettingOut])
async def get_settings():
    """
    获取所有系统设置
    """
    return load_settings_for_output()


@router.post("", response_model=SettingOut)
async def update_setting(payload: SettingUpdate):
    """
    更新系统设置
    """
    try:
        updated = update_setting_value(payload.key, payload.value)
        return serialize_setting_for_output(updated)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Setting {payload.key} not found")


@router.post("/test-connection", response_model=LLMTestOut)
async def test_llm_connection(payload: LLMTestRequest):
    """
    测试 LLM API 连接是否正常
    """
    api_url = normalize_llm_api_url(payload.api_url)
    api_key = payload.api_key
    model = payload.model

    if api_key == "__use_saved__":
        api_key = get_llm_settings_map().get("LLM_API_KEY", "")

    if not api_url or not api_key:
        raise HTTPException(status_code=400, detail="API URL 和 API Key 不能为空")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # 构建一个简单的测试请求
    test_payload = {
        "model": model or "gpt-3.5-turbo",
        "messages": [{"role": "user", "content": "Hi"}],
        "max_tokens": 5,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # 判断是否是 Responses API
            if api_url.rstrip("/").endswith("/responses"):
                test_payload = {
                    "model": model or "gpt-4o-mini",
                    "input": [{"role": "user", "content": [{"type": "input_text", "text": "Hi"}]}],
                    "max_output_tokens": 5,
                }
                resp = await client.post(api_url, headers=headers, json=test_payload)
            else:
                resp = await client.post(api_url, headers=headers, json=test_payload)

            resp.raise_for_status()
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
        else:
            return LLMTestOut(success=False, message=f"HTTP {status}: {str(e)}")
    except httpx.ConnectError:
        return LLMTestOut(success=False, message="无法连接到 API 服务器，请检查网络或地址")
    except httpx.TimeoutException:
        return LLMTestOut(success=False, message="连接超时，请检查网络或稍后重试")
    except Exception as e:
        return LLMTestOut(success=False, message=f"测试失败：{str(e)}")


@router.get("/models", response_model=List[LLMModelOut])
async def get_available_models():
    """
    获取当前 API 支持的模型列表
    """
    try:
        settings = get_llm_settings_map()
        api_url = normalize_llm_api_url(settings.get("LLM_API_URL", ""))
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

            models = []
            model_list = data.get("data", [])
            for m in model_list:
                model_id = m.get("id", "")
                if model_id:
                    models.append(LLMModelOut(id=model_id, name=model_id))

            # 按名称排序
            models.sort(key=lambda x: x.id)
            return models

    except Exception as e:
        # 静默失败，返回空列表
        return []
