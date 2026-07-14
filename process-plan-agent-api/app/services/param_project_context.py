from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Document, Project, Reference

StageT = TypeVar("StageT")

_PARAM_JSON_STAGE_CACHE: dict[tuple[str, int, int], list[object]] = {}


@dataclass
class ProjectResourceBundle:
    project: Project | None
    documents: list[Document]
    references: list[Reference]


@dataclass
class ParsedParamJsonDocument(Generic[StageT]):
    document: Document
    filepath: Path
    stages: list[StageT]


@dataclass
class ParamJsonContext(Generic[StageT]):
    json_documents: list[Document]
    selected_document: Document | None
    parsed_json_documents: list[ParsedParamJsonDocument[StageT]]
    sample_stages: list[StageT]
    superset_stages: list[StageT]


async def load_project_resource_bundle(
    project_id: int,
    db: AsyncSession,
) -> ProjectResourceBundle:
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    docs_result = await db.execute(
        select(Document)
        .where(Document.project_id == project_id)
        .order_by(Document.created_at.asc(), Document.id.asc())
    )
    refs_result = await db.execute(
        select(Reference)
        .where(Reference.project_id == project_id)
        .order_by(Reference.created_at.asc(), Reference.id.asc())
    )
    return ProjectResourceBundle(
        project=project,
        documents=docs_result.scalars().all(),
        references=refs_result.scalars().all(),
    )


def build_param_json_context(
    documents: list[Document],
    upload_dir: Path,
    read_raw_text_with_fallbacks: Callable[[str], str],
    build_param_sample_stages: Callable[[str], list[StageT]],
    build_param_superset_stages: Callable[[list[list[StageT]]], list[StageT]],
    document_id: int | None = None,
) -> ParamJsonContext[StageT]:
    json_documents = [doc for doc in documents if (doc.file_type or "").lower() == "json"]
    selected_document = None
    if document_id is not None:
        selected_document = next((doc for doc in json_documents if doc.id == document_id), None)
    if selected_document is None and json_documents:
        selected_document = json_documents[0]

    parsed_json_documents: list[ParsedParamJsonDocument[StageT]] = []
    sample_stages: list[StageT] = []
    all_stage_lists: list[list[StageT]] = []

    for json_doc in json_documents:
        if not json_doc.filename:
            continue
        filepath = upload_dir / json_doc.filename
        if not filepath.exists():
            continue
        signature = _file_signature(filepath)
        cached = _PARAM_JSON_STAGE_CACHE.get(signature)
        if cached is None:
            raw_text = read_raw_text_with_fallbacks(str(filepath))
            cached = list(build_param_sample_stages(raw_text))
            _PARAM_JSON_STAGE_CACHE[signature] = cached
        stages = list(cached)
        if stages:
            all_stage_lists.append(stages)
        if selected_document and json_doc.id == selected_document.id:
            sample_stages = stages
        parsed_json_documents.append(
            ParsedParamJsonDocument(
                document=json_doc,
                filepath=filepath,
                stages=stages,
            )
        )

    return ParamJsonContext(
        json_documents=json_documents,
        selected_document=selected_document,
        parsed_json_documents=parsed_json_documents,
        sample_stages=sample_stages,
        superset_stages=build_param_superset_stages(all_stage_lists),
    )


async def build_param_json_context_async(
    documents: list[Document],
    upload_dir: Path,
    read_raw_text_with_fallbacks: Callable[[str], str],
    build_param_sample_stages: Callable[[str], list[StageT]],
    build_param_superset_stages: Callable[[list[list[StageT]]], list[StageT]],
    document_id: int | None = None,
) -> ParamJsonContext[StageT]:
    return await asyncio.to_thread(
        build_param_json_context,
        documents,
        upload_dir,
        read_raw_text_with_fallbacks,
        build_param_sample_stages,
        build_param_superset_stages,
        document_id,
    )


def build_param_sample_pairs_from_context(
    documents: list[Document],
    parsed_json_documents: list[ParsedParamJsonDocument[StageT]],
    sample_key_for_document: Callable[[Document], str],
    extract_document_body: Callable[[Document], str],
    parse_reference_attributes: Callable[[str], dict[str, str]],
) -> list[dict[str, object]]:
    param_docs: dict[str, dict[str, str]] = {}
    json_docs = {
        sample_key_for_document(item.document): list(item.stages)
        for item in parsed_json_documents
        if sample_key_for_document(item.document)
    }

    for doc in documents:
        file_type = (doc.file_type or "").lower()
        if file_type == "json":
            continue
        sample_key = sample_key_for_document(doc)
        if not sample_key:
            continue
        attrs = parse_reference_attributes(extract_document_body(doc))
        if attrs:
            param_docs[sample_key] = attrs

    pairs: list[dict[str, object]] = []
    for sample_key in sorted(set(param_docs.keys()) & set(json_docs.keys())):
        pairs.append(
            {
                "sample_key": sample_key,
                "attrs": param_docs[sample_key],
                "stages": json_docs[sample_key],
            }
        )
    return pairs


def _file_signature(filepath: Path) -> tuple[str, int, int]:
    stat = filepath.stat()
    return (str(filepath), int(stat.st_mtime_ns), int(stat.st_size))
