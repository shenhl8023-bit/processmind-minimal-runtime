"""
文档级工序明细抽取服务的对外入口。

当前普通 PDF 解析实现已经拆分到独立模块，避免一个文件同时承担
类型定义、文本清洗、表格解析和对外导出四类职责。
"""

from __future__ import annotations

from app.services.document_operation_detail_types import ExtractedOperationDetail, OperationRow
from app.services.document_operation_pdf_parser import (
    extract_pdf_operation_details,
    extract_pdf_operation_rows,
    merge_pdf_operation_rows,
    normalize_spaces,
    strip_noise_suffixes,
)


__all__ = [
    "ExtractedOperationDetail",
    "OperationRow",
    "extract_pdf_operation_details",
    "extract_pdf_operation_rows",
    "merge_pdf_operation_rows",
    "normalize_spaces",
    "strip_noise_suffixes",
]
