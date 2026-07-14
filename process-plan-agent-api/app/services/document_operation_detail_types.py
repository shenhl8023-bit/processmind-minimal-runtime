"""
文档级工序明细抽取的共享类型定义。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ExtractedOperationDetail:
    operation_seq: int
    operation_name: str
    operation_content: str
    page_no: int | None = None
    item_no: str = ""
    normalized_name: str = ""
    is_composite: bool = False
    source_type: str = "pdf_table_extract"
    equipment_types: str = ""
    equipment_models: str = ""


@dataclass
class OperationRow:
    process_no: int
    process_name: str
    item_no: str
    content: str
    page_no: int
    equipment_types: str = ""
    equipment_models: str = ""


__all__ = ["ExtractedOperationDetail", "OperationRow"]
