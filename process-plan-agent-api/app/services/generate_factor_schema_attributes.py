"""Extract part attributes from uploaded process-document text."""

from __future__ import annotations

import os
import re

from app.core.paths import UPLOAD_DIR
from app.models.models import Document
from app.services.file_parser import extract_text


def parse_document_attributes(text: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for raw_line in (text or "").splitlines():
        line = re.sub(r"\s+", "", raw_line).strip()
        if not line or "|" not in line:
            continue
        parts = [part.strip() for part in line.split("|") if part.strip()]
        if len(parts) >= 3 and parts[0].isdigit():
            key, value = parts[1], parts[2]
        elif len(parts) >= 2:
            key, value = parts[0], parts[1]
        else:
            continue
        if key in {"序号", "参数", "参数值", "工作表", "[工作表:Sheet1]"}:
            continue
        if len(key) <= 40 and len(value) <= 80:
            attrs.setdefault(key, value)
    return attrs


def extract_document_body(doc: Document) -> str:
    if not doc.filename:
        return ""
    filepath = os.path.join(UPLOAD_DIR, doc.filename)
    return extract_text(filepath, doc.file_type or None).strip()


__all__ = ["extract_document_body", "parse_document_attributes"]
