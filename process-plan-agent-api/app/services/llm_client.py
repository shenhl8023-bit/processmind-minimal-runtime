"""
LLM 客户端能力：配置解析、请求构造、重试与响应文本提取。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os

import httpx
from dotenv import load_dotenv

from app.services.settings_store import get_llm_settings_map
from app.services.llm_errors import LLMResponseError, tls_error_cause

load_dotenv(override=True)

logger = logging.getLogger(__name__)

DEFAULT_LLM_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
DEFAULT_LLM_MODEL = "meta/llama-3.1-70b-instruct"
DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS = 180.0
DEFAULT_LLM_MAX_RETRIES = 2


def llm_request_timeout_seconds(override: float | None = None) -> float:
    """Return the provider timeout without allowing an accidental zero value."""
    try:
        value = float(
            override
            if override is not None
            else os.getenv("LLM_REQUEST_TIMEOUT_SECONDS", str(DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS))
        )
    except (TypeError, ValueError):
        return DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS
    return max(5.0, min(value, 300.0))


def llm_max_retries(override: int | None = None) -> int:
    """Return the number of retries after the initial request."""
    try:
        value = int(
            override
            if override is not None
            else os.getenv("LLM_MAX_RETRIES", str(DEFAULT_LLM_MAX_RETRIES))
        )
    except (TypeError, ValueError):
        return DEFAULT_LLM_MAX_RETRIES
    return max(0, min(value, 3))


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
        if "LLM_API_URL" in file_settings:
            config["url"] = file_settings["LLM_API_URL"]
        if "LLM_API_KEY" in file_settings:
            config["key"] = file_settings["LLM_API_KEY"]
        if "LLM_MODEL" in file_settings:
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
    saw_data = False
    saw_text = False

    for line in lines:
        if not line.startswith("data:"):
            continue
        saw_data = True
        payload = line[5:].strip()
        if not payload:
            continue
        try:
            item = json.loads(payload)
        except json.JSONDecodeError:
            continue

        if not isinstance(item, dict):
            continue
        event_type = item.get("type")
        if event_type in ("response.refusal.delta", "response.refusal.done"):
            _response_error("refused")
        if event_type in ("error", "response.failed"):
            _response_error("invalid")
        if event_type == "response.incomplete":
            _response_error("truncated")
        if event_type == "response.completed":
            response = item.get("response")
            done_text = _checked_response_text(response, responses=True)
            saw_text = True

        if event_type == "response.output_text.delta":
            delta = item.get("delta")
            if isinstance(delta, str):
                deltas.append(delta)
                saw_text = True
        elif event_type == "response.output_text.done":
            text = item.get("text")
            if isinstance(text, str):
                done_text = text
                saw_text = True

    if saw_data and not saw_text:
        _response_error("invalid")
    return done_text or "".join(deltas)


def _extract_text_from_chat_completion_json(payload: object) -> str:
    """Extract text from current and legacy Chat Completions response shapes."""
    if not isinstance(payload, dict):
        return ""
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return ""

    choice = choices[0]
    message = choice.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        chunks = [
            part["text"]
            for part in content
            if isinstance(part, dict)
            and part.get("type") in {None, "text", "output_text"}
            and isinstance(part.get("text"), str)
        ]
        if chunks:
            return "".join(chunks).strip()

    # Older completion-compatible gateways return choices[].text.
    legacy_text = choice.get("text")
    return legacy_text.strip() if isinstance(legacy_text, str) else ""


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
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    # A few OpenAI-compatible gateways expose a Responses URL while still
    # returning the Chat Completions envelope.
    return _extract_text_from_chat_completion_json(payload)


def _response_error(reason: str, payload=None):
    """Log fixed metadata only, never arbitrary provider values or response text."""
    body = payload if isinstance(payload, dict) else {}
    choices = body.get("choices")
    choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
    message = choice.get("message")
    message = message if isinstance(message, dict) else {}
    finish = choice.get("finish_reason")
    finish = finish if isinstance(finish, str) and finish in {"stop", "length", "content_filter", "tool_calls"} else "other"
    content, reasoning = message.get("content"), message.get("reasoning_content")
    logger.warning("LLM response unusable reason=%s choices=%s finish=%s content_length=%s reasoning_length=%s",
                   reason, len(choices) if isinstance(choices, list) else 0, finish,
                   len(content) if isinstance(content, (str, list)) else 0,
                   len(reasoning) if isinstance(reasoning, str) else 0)
    raise LLMResponseError(reason=reason)


def _checked_response_text(payload, *, responses=False) -> str:
    if not isinstance(payload, dict):
        _response_error("invalid")
    choices = payload.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        choice = choices[0]
        message = choice.get("message")
        message = message if isinstance(message, dict) else {}
        if choice.get("finish_reason") == "length":
            _response_error("truncated", payload)
        if choice.get("finish_reason") == "content_filter" or message.get("refusal"):
            _response_error("refused", payload)
        if not ("content" in message or isinstance(choice.get("text"), str)):
            _response_error("invalid", payload)
        if message.get("tool_calls") or not isinstance(message.get("content"), (str, list, type(None))):
            _response_error("invalid", payload)
        parts = message.get("content")
        if isinstance(parts, list) and parts:
            if any(isinstance(part, dict) and part.get("type") == "refusal" for part in parts):
                _response_error("refused", payload)
            if not any(isinstance(part, dict) and part.get("type") in (None, "text", "output_text")
                       and isinstance(part.get("text"), str) for part in parts):
                _response_error("invalid", payload)
        text = _extract_text_from_chat_completion_json(payload)
    elif responses and (isinstance(payload.get("output"), list) or isinstance(payload.get("output_text"), str)):
        if payload.get("status") == "incomplete":
            _response_error("truncated", payload)
        if payload.get("status") == "failed":
            _response_error("invalid", payload)
        output = payload.get("output")
        items = output if isinstance(output, list) else []
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("content"), list):
                continue
            if any(isinstance(part, dict) and part.get("type") == "refusal" for part in item["content"]):
                _response_error("refused", payload)
        text = extract_text_from_responses_json(payload)
        if not text and items:
            for item in items:
                if isinstance(item, dict) and item.get("type") == "reasoning":
                    continue
                if not isinstance(item, dict) or item.get("type") != "message" or not isinstance(item.get("content"), list):
                    _response_error("invalid", payload)
                if any(not isinstance(part, dict) or part.get("type") != "output_text"
                       or not isinstance(part.get("text"), str) for part in item["content"]):
                    _response_error("invalid", payload)
    else:
        _response_error("invalid", payload)
    if not text.strip():
        _response_error("empty", payload)
    return text


def _require_response_text(text: str) -> str:
    if not isinstance(text, str) or not text.strip():
        _response_error("empty")
    return text


def _extract_text_from_responses_lines(lines: list[str]) -> str:
    """Extract text from either Responses SSE or a JSON body read as lines."""
    sse_text = _extract_text_from_responses_sse(lines)
    if any(line.startswith("data:") for line in lines):
        return sse_text
    body = "\n".join(lines).strip()
    if not body:
        _response_error("invalid")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        _response_error("invalid")
    return _checked_response_text(payload, responses=True)


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
    max_tokens: int = 4096,
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
            "max_output_tokens": max_tokens,
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
        "max_tokens": max_tokens,
    }


async def request_llm_completion(
    config: dict[str, str],
    system_prompt: str,
    user_prompt: str,
    *,
    temperature: float = 0.2,
    timeout_seconds: float | None = None,
    max_retries: int | None = None,
    max_tokens: int = 4096,
) -> str:
    headers = _build_headers(config["key"])
    payload = _build_completion_payload(
        url=config["url"],
        model=config["model"],
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    last_error: Exception | None = None
    max_attempts = 1 + llm_max_retries(max_retries)
    empty_retried = False
    async with httpx.AsyncClient(timeout=llm_request_timeout_seconds(timeout_seconds)) as client:
        for attempt in range(max_attempts):
            try:
                if is_responses_api_url(config["url"]):
                    async with client.stream("POST", config["url"], headers=headers, json=payload) as resp:
                        resp.raise_for_status()
                        lines = [line async for line in resp.aiter_lines() if line]
                    return _require_response_text(_extract_text_from_responses_lines(lines))
                resp = await client.post(config["url"], headers=headers, json=payload)
                resp.raise_for_status()
                try:
                    data = resp.json()
                except ValueError:
                    _response_error("invalid")
                return _checked_response_text(data)
            except LLMResponseError as exc:
                # Retry only a recognized empty answer, once and within the
                # caller's existing attempt/deadline budget. Never use reasoning.
                if exc.reason == "empty" and not empty_retried and attempt < max_attempts - 1:
                    empty_retried = True
                    await asyncio.sleep(2)
                    continue
                raise
            except httpx.HTTPStatusError as exc:
                last_error = exc
                status = exc.response.status_code
                if status in (429, 500, 502, 503, 504) and attempt < max_attempts - 1:
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                raise
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_error = exc
                if tls_error_cause(exc) is not None:
                    raise
                if attempt < max_attempts - 1:
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
                try:
                    data = resp.json()
                except ValueError:
                    _response_error("invalid")
                return _checked_response_text(data, responses=True)
            except httpx.HTTPStatusError as exc:
                last_error = exc
                if exc.response.status_code in (429, 500, 502, 503, 504) and attempt < 1:
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                raise
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_error = exc
                if tls_error_cause(exc) is not None:
                    raise
                if attempt < 1:
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                raise

    if last_error:
        raise last_error
    return ""
