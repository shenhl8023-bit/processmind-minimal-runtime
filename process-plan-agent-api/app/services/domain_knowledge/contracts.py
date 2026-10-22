"""Portable domain resources. Uploaded prose is data, never instructions."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from app.services.rule_packages.contracts import ConditionNode, InputField


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Scope(Strict):
    part_families: list[str] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)
    stages: list[str] = Field(default_factory=list)


class SourceRef(Strict):
    source_id: str = Field(min_length=1)
    heading_path: list[str] = Field(default_factory=list)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)


class Source(Strict):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=False)
    id: str = Field(min_length=1)
    filename: str = Field(min_length=1)
    content: str
    content_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    verification_status: Literal['unverified', 'verified', 'example', 'obsolete'] = 'unverified'


class Resource(Strict):
    id: str = Field(min_length=1, max_length=200, pattern=r'^[\w.:-]+$')
    name: str = Field(min_length=1)
    applicability: Scope
    source_refs: list[SourceRef] = Field(min_length=1)
    review_status: Literal['needs_review', 'accepted', 'rejected'] = 'needs_review'
    reviewed_by: str = ''
    confidence: float = Field(default=0, ge=0, le=1)
    uncertainty: list[str] = Field(default_factory=list)


class Concept(Resource):
    concept_type: Literal['process', 'material', 'feature', 'stage', 'part_family', 'other']
    definition: str = ''
    aliases: list[str] = Field(default_factory=list)


class Relation(Resource):
    relation_type: Literal['synonym', 'is_a', 'part_of', 'before', 'keep_separate', 'absorb_into']
    source_concept_id: str
    target_concept_id: str
    condition: ConditionNode | None = None


class Factor(Resource):
    field: InputField


class RuleCandidate(Resource):
    condition: ConditionNode
    target_concept_id: str
    conclusion: Literal['include', 'exclude']
    explanation: str = Field(min_length=1)


class RouteTemplate(Resource):
    concept_ids: list[str] = Field(min_length=1)
    optional: bool = True


RESOURCE_TYPES = ('concepts', 'relations', 'factors', 'rule_candidates', 'route_templates')


class DomainKnowledgePackageDraft(Strict):
    package_id: str = Field(pattern=r'^[a-zA-Z0-9][\w.-]{0,99}$')
    name: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    part_family_scope: list[str] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    concepts: list[Concept] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    factors: list[Factor] = Field(default_factory=list)
    rule_candidates: list[RuleCandidate] = Field(default_factory=list)
    route_templates: list[RouteTemplate] = Field(default_factory=list)


class PackageRef(Strict):
    package_id: str
    version: int = Field(gt=0)
    content_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
