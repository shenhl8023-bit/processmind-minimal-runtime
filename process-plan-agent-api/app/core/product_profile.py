"""Small, offline build profile shared by business guards and the UI.

Only fixed-offset datetime is used so the Win7 Python 3.8 bundle needs no
zoneinfo database, new native dependency, or network time service.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
import json
import os
from pathlib import Path
from typing import Optional

from app.core.paths import PROJECT_ROOT


TRIAL_EXPIRED_MESSAGE = "试用已到期，请联系供应方。"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ProductProfile:
    edition: str
    # License capability: API guards and stored mapping compatibility use this.
    template_mapping_enabled: bool
    expires_at: Optional[datetime]
    template_mapping_visible: bool = True

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        return self.expires_at is not None and (now if now is not None else utc_now()) >= self.expires_at

    def status(self) -> dict:
        now = utc_now()
        return {
            "edition": self.edition,
            "template_mapping_enabled": self.template_mapping_enabled and self.template_mapping_visible,
            "expires_at": self.expires_at.isoformat() if self.expires_at is not None else None,
            "expired": self.is_expired(now),
            "server_time": now.isoformat(),
        }


@lru_cache(maxsize=1)
def get_product_profile() -> ProductProfile:
    configured = os.getenv("PROCESSMIND_PROFILE_PATH", "").strip()
    path = Path(configured).expanduser() if configured else PROJECT_ROOT / "product-profile.json"
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict) or set(data) != {"edition", "template_mapping_enabled", "expires_at"}:
            raise ValueError("配置字段不完整或不支持")
        edition = data["edition"]
        enabled = data["template_mapping_enabled"]
        if edition not in {"full", "basic-trial"} or not isinstance(enabled, bool):
            raise ValueError("版本或功能配置无效")
        if enabled != (edition == "full"):
            raise ValueError("版本与功能配置不一致")
        expires_at = None
        raw_expiry = data["expires_at"]
        if edition == "basic-trial":
            if not isinstance(raw_expiry, str) or not raw_expiry.strip():
                raise ValueError("试用版必须包含到期时间")
            expires_at = datetime.fromisoformat(raw_expiry.replace("Z", "+00:00"))
            if expires_at.tzinfo is None or expires_at.utcoffset() is None:
                raise ValueError("到期时间必须包含时区")
        elif raw_expiry is not None:
            raise ValueError("完整版不使用试用到期时间")
    except (OSError, ValueError, TypeError) as exc:
        raise RuntimeError("产品配置无效，无法启动：%s" % path) from exc
    return ProductProfile(edition, enabled, expires_at, _read_template_mapping_visibility())


def _read_template_mapping_visibility() -> bool:
    """Read deployment UI configuration once through the cached profile loader."""
    configured = os.getenv("PROCESSMIND_FEATURES_PATH", "").strip()
    path = Path(configured).expanduser() if configured else PROJECT_ROOT / "product-features.json"
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    try:
        try:
            contents = path.read_text(encoding="utf-8-sig")
        except FileNotFoundError:
            if configured:
                raise
            return True
        data = json.loads(contents)
        if not isinstance(data, dict) or not set(data).issubset({"template_mapping_enabled"}):
            raise ValueError("不支持的功能配置字段")
        enabled = data.get("template_mapping_enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError("template_mapping_enabled 必须为布尔值")
        return enabled
    except (OSError, ValueError, TypeError) as exc:
        raise RuntimeError("产品功能配置无效，无法启动：%s" % path) from exc
