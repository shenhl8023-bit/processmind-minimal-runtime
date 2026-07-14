"""
LLM 客户端能力：配置解析、请求构造、重试与响应文本提取。
"""
import asyncio
import json
import logging
import os

import httpx
from dotenv import load_dotenv

from app.services.settings_store import get_llm_settings_map

load_dotenv(override=True)

logger = logging.getLogger(__name__)

DEFAULT_LLM_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
DEFAULT_LLM_MODEL = "meta/llama-3.1-70b-instruct"


def _get_env_with_alias(key: str, alias: str, default: str = "") -> str:
    return os.getenv(key) or os.getenv(alias) or default


def normalize_llm_api_url(url: str) -> str:
    """
    Accept either a provider base URL (/v1) or a concrete endpoint.
    """
    clean_url = (url or "").strip().rstrip("/")
    if not clean_url:
        return clean_url
    if clean_url.endswith(("/chat/completions", "/responses")):
        return clean_url
    if clean_url.endswith("/v1"):
        return f"{clean_url}/chat/completions"
    return f"{clean_url}/chat/completions"


async def get_llm_config() -> dict[str, str]:
    """
    优先从独立设置文件获取配置，如果设置文件没有则从环境变量获取。
    """
    config = {
        "url": _get_env_with_alias("LLM_API_URL", "OPENAI_BASE_URL", DEFAULT_LLM_URL),
        "key": _get_env_with_alias("LLM_API_KEY", "OPENAI_API_KEY", ""),
        "model": _get_env_with_alias("LLM_MODEL", "OPENAI_MODEL", DEFAULT_LLM_MODEL),
    }

    try:
        file_settings = get_llm_settings_map()
        if file_settings.get("LLM_API_URL"):
            config["url"] = file_settings["LLM_API_URL"]
        if file_settings.get("LLM_API_KEY"):
            config["key"] = file_settings["LLM_API_KEY"]
        if file_settings.get("LLM_MODEL"):
            config["model"] = file_settings["LLM_MODEL"]
    except Exception:
        logger.exception("Failed to fetch LLM config from settings store")

    config["url"] = normalize_llm_api_url(config["url"])
    return config


def is_llm_web_search_enabled() -> bool:
    raw_value = os.getenv("LLM_WEB_SEARCH_ENABLED", "false")
    return str(raw_value).strip().lower() in {"1", "true", "yes", "on"}


def is_responses_api_url(url: str) -> bool:
    return url.rstrip("/").endswith("/responses")


def _extract_text_from_responses_sse(lines: list[str]) -> str:
    deltas: list[str] = []
    done_text = ""

    for line in lines:
        if not line.startswith("data: "):
            continue
        payload = line[6:].strip()
        if not payload:
            continue
        try:
            item = json.loads(payload)
        except json.JSONDecodeError:
            continue

        if item.get("type") == "response.output_text.delta":
            delta = item.get("delta")
            if isinstance(delta, str):
                deltas.append(delta)
        elif item.get("type") == "response.output_text.done":
            text = item.get("text")
            if isinstance(text, str):
                done_text = text

    return done_text or "".join(deltas)


def extract_text_from_responses_json(payload: dict) -> str:
    output = payload.get("output")
    if isinstance(output, list):
        chunks: list[str] = []
        for item in output:
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            contents = item.get("content")
            if not isinstance(contents, list):
                continue
            for content in contents:
                if not isinstance(content, dict):
                    continue
                if content.get("type") == "output_text":
                    text = content.get("text")
                    if isinstance(text, str) and text:
                        chunks.append(text)
        if chunks:
            return "\n".join(chunks).strip()

    output_text = payload.get("output_text")
    return output_text.strip() if isinstance(output_text, str) else ""


def _build_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _build_completion_payload(
    *,
    url: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    web_search_enabled: bool = False,
) -> dict:
    if is_responses_api_url(url):
        payload = {
            "model": model,
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": system_prompt}],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": user_prompt}],
                },
            ],
            "temperature": temperature,
            "max_output_tokens": 4096,
            "stream": not web_search_enabled,
        }
        if web_search_enabled:
            payload["tools"] = [{"type": "web_search"}]
        return payload

    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": 4096,
    }


async def request_llm_completion(
    config: dict[str, str],
    system_prompt: str,
    user_prompt: str,
    *,
    temperature: float = 0.2,
) -> str:
    headers = _build_headers(config["key"])
    payload = _build_completion_payload(
        url=config["url"],
        model=config["model"],
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=temperature,
    )

    last_error: Exception | None = None
    async with httpx.AsyncClient(timeout=180.0) as client:
        for attempt in range(3):
            try:
                if is_responses_api_url(config["url"]):
                    async with client.stream("POST", config["url"], headers=headers, json=payload) as resp:
                        resp.raise_for_status()
                        lines = [line async for line in resp.aiter_lines() if line]
                    return _extract_text_from_responses_sse(lines)
                resp = await client.post(config["url"], headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            except httpx.HTTPStatusError as exc:
                last_error = exc
                status = exc.response.status_code
                if status in (429, 500, 502, 503, 504) and attempt < 2:
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                raise
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_error = exc
                if attempt < 2:
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                raise

    if last_error:
        raise last_error
    return ""


async def request_llm_completion_with_web_search(
    config: dict[str, str],
    system_prompt: str,
    user_prompt: str,
    *,
    temperature: float = 0.2,
) -> str:
    if not is_responses_api_url(config["url"]):
        raise ValueError("当前模型接口不是 Responses API，无法启用内置 web_search。")

    headers = _build_headers(config["key"])
    payload = _build_completion_payload(
        url=config["url"],
        model=config["model"],
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=temperature,
        web_search_enabled=True,
    )

    last_error: Exception | None = None
    async with httpx.AsyncClient(timeout=180.0) as client:
        for attempt in range(2):
            try:
                resp = await client.post(config["url"], headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                return extract_text_from_responses_json(data)
            except httpx.HTTPStatusError as exc:
                last_error = exc
                if exc.response.status_code in (429, 500, 502, 503, 504) and attempt < 1:
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                raise
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_error = exc
                if attempt < 1:
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                raise

    if last_error:
        raise last_error
    return ""
