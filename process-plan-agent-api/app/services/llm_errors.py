"""Safe model error descriptions shared by settings and analysis callers."""
from __future__ import annotations

import asyncio
import ssl
from typing import Optional, Tuple

import httpx


class LLMResponseError(ValueError):
    """A provider response was unusable; retain only a safe enumerated reason."""

    def __init__(self, message="LLM response did not contain text", *, reason="invalid"):
        self.reason = reason if reason in {"empty", "truncated", "refused", "invalid"} else "invalid"
        super().__init__(message)


def tls_error_cause(error: BaseException) -> Optional[ssl.SSLError]:
    """HTTPX wraps TLS errors several times; inspect types, never provider text."""
    pending = [error]
    visited = set()
    while pending:
        current = pending.pop()
        if id(current) in visited:
            continue
        visited.add(id(current))
        if isinstance(current, ssl.SSLError):
            return current
        for parent in (current.__cause__, current.__context__):
            if isinstance(parent, BaseException):
                pending.append(parent)
    return None


def describe_llm_error(error: Exception) -> Tuple[str, str]:
    """Return public text without URLs, provider response bodies or credentials."""
    tls = tls_error_cause(error)
    if isinstance(tls, ssl.SSLCertVerificationError):
        return 'llm_tls_certificate_invalid', '模型服务证书校验失败，请检查服务证书或系统时间。'
    if tls is not None:
        return 'llm_tls_failed', '模型服务的 HTTPS 安全连接失败，请检查模型服务或网络链路。'
    if isinstance(error, (asyncio.TimeoutError, httpx.TimeoutException)):
        return 'llm_timeout', '模型请求超时，请检查网络或稍后重试。'
    if isinstance(error, httpx.ConnectError):
        return 'llm_connect_failed', '无法连接到 API 服务器，请检查网络或地址。'
    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        known = {
            401: ('llm_auth_failed', '认证失败：API Key 无效或已过期'),
            403: ('llm_permission_denied', '权限不足：请检查 API Key 权限'),
            404: ('llm_endpoint_not_found', '接口地址错误或模型不存在'),
            429: ('llm_rate_limited', '请求过于频繁，请稍后重试'),
        }
        if status in known:
            return known[status]
        if status in (500, 502, 503, 504):
            return 'llm_service_unavailable', '模型服务暂时不可用，请稍后重试。'
        return 'llm_http_error', '模型服务返回 HTTP %s，请检查接口配置。' % status
    if isinstance(error, httpx.HTTPError):
        return 'llm_request_failed', '无法完成模型请求，请检查网络或接口地址。'
    if isinstance(error, LLMResponseError):
        descriptions = {
            'empty': ('llm_empty_response', '模型未返回有效正文，请稍后重试。'),
            'truncated': ('llm_output_truncated', '模型输出达到长度限制，未完整生成，请重试或调整模型输出限制。'),
            'refused': ('llm_response_refused', '模型拒绝了本次请求，未生成可用答案，请检查请求或更换模型后重试。'),
        }
        if error.reason in descriptions:
            return descriptions[error.reason]
    if isinstance(error, (KeyError, TypeError, ValueError)):
        return 'llm_response_invalid', '模型服务返回了无法识别的响应，请重试；持续失败时请检查接口配置。'
    return 'llm_request_failed', '模型请求失败，请检查配置后重试。'
