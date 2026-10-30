"""Read-only catalog contracts, compatible with CPython 3.8."""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CatalogOption(BaseModel):
    value: str
    label: str
    count: int


class CatalogColumn(BaseModel):
    key: str
    label: str


class CatalogRow(BaseModel):
    id: str
    title: str
    category: str
    source_kind: str
    source_label: str
    verification_status: str
    data_warnings: List[str] = Field(default_factory=list)
    values: Dict[str, str]


class CatalogResponse(BaseModel):
    section: str
    total: int
    raw_count: int
    page: int
    page_size: int
    categories: List[CatalogOption]
    topics: List[CatalogOption]
    columns: List[CatalogColumn]
    items: List[CatalogRow]


class CatalogDetail(CatalogRow):
    fields: Dict[str, Any]
    sources: List[Dict[str, Any]]
    guidance: Optional[Dict[str, Any]] = None
    original_records: List[Dict[str, Any]]
