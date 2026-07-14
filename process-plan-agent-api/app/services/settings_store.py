"""
独立的系统设置存储。
将模型配置从工艺任务数据库中解耦，避免清空任务库时一并丢失。
"""
from __future__ import annotations

import json
import os
from datetime import datetime

from app.core.paths import SETTINGS_FILE_PATH

SETTINGS_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)

SETTING_DEFINITIONS = [
    ("LLM_API_URL", "LLM API 地址", "https://integrate.api.nvidia.com/v1/chat/completions"),
    ("LLM_API_KEY", "LLM API Key", ""),
    ("LLM_MODEL", "LLM 模型名称", "meta/llama-3.1-70b-instruct"),
    ("KNOWLEDGE_SEARCH_PROVIDER", "工艺知识检索提供方", "tavily"),
    ("KNOWLEDGE_SEARCH_API_URL", "工艺知识检索 API 地址", "https://api.tavily.com/search"),
    ("KNOWLEDGE_SEARCH_API_KEY", "工艺知识检索 API Key", ""),
]

SECRET_SETTING_KEYS = {
    "LLM_API_KEY",
    "KNOWLEDGE_SEARCH_API_KEY",
}

ENV_ALIASES = {
    "LLM_API_URL": ("OPENAI_BASE_URL",),
    "LLM_API_KEY": ("OPENAI_API_KEY",),
    "LLM_MODEL": ("OPENAI_MODEL",),
}


def _env_value(key: str, default: str = "") -> str:
    value = os.getenv(key, "")
    if value:
        return value
    for alias in ENV_ALIASES.get(key, ()):
        value = os.getenv(alias, "")
        if value:
            return value
    return default


def _default_settings_map() -> dict[str, dict[str, str]]:
    return {
        key: {
            "key": key,
            "value": _env_value(key, default_value),
            "description": description,
        }
        for key, description, default_value in SETTING_DEFINITIONS
    }


def _normalize_settings_payload(payload: dict[str, dict[str, str]]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for idx, (key, description, _) in enumerate(SETTING_DEFINITIONS, start=1):
        row = payload.get(key) or {}
        normalized.append(
            {
                "id": idx,
                "key": key,
                "value": str(row.get("value") or _env_value(key)),
                "description": str(row.get("description") or description),
                "updated_at": str(row.get("updated_at") or datetime.now().isoformat()),
            }
        )
    return normalized


def load_settings() -> list[dict[str, str]]:
    if os.path.isfile(SETTINGS_FILE_PATH):
        try:
            with open(SETTINGS_FILE_PATH, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if isinstance(payload, list):
                by_key = {
                    str(item.get("key") or ""): {
                        "value": str(item.get("value") or ""),
                        "description": str(item.get("description") or ""),
                        "updated_at": str(item.get("updated_at") or ""),
                    }
                    for item in payload
                    if isinstance(item, dict) and item.get("key")
                }
                return _normalize_settings_payload(by_key)
        except Exception:
            pass

    base = _default_settings_map()
    settings = _normalize_settings_payload(base)
    save_settings(settings)
    return settings


def serialize_setting_for_output(row: dict[str, str]) -> dict[str, str | bool]:
    is_secret = row["key"] in SECRET_SETTING_KEYS
    return {
        **row,
        "value": "" if is_secret else row["value"],
        "is_secret": is_secret,
        "is_configured": bool(str(row["value"]).strip()),
    }


def load_settings_for_output() -> list[dict[str, str | bool]]:
    return [serialize_setting_for_output(row) for row in load_settings()]


def save_settings(settings: list[dict[str, str]]) -> None:
    with open(SETTINGS_FILE_PATH, "w", encoding="utf-8") as handle:
        json.dump(settings, handle, ensure_ascii=False, indent=2)


def update_setting_value(key: str, value: str) -> dict[str, str]:
    settings = load_settings()
    updated: dict[str, str] | None = None
    now = datetime.now().isoformat()
    for row in settings:
        if row["key"] != key:
            continue
        # 密钥字段传入空值时跳过，保留已有值
        if key in SECRET_SETTING_KEYS and not value.strip():
            updated = row
            break
        row["value"] = value
        row["updated_at"] = now
        updated = row
        break
    if updated is None:
        raise KeyError(key)
    save_settings(settings)
    return updated


def get_llm_settings_map() -> dict[str, str]:
    settings = load_settings()
    return {row["key"]: row["value"] for row in settings}
