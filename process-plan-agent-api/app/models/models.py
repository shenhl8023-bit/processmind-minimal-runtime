"""
ORM 数据模型 —— 对应 database_schema.md 中设计的核心表
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, Float
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base


def utcnow():
    return datetime.now(timezone.utc)


# ---------- 项目 / 任务 ----------
class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    mode = Column(String(50), default="route_rules")
    profile = Column(String(100), default="route_rules.document_rules")
    rule_engine = Column(String(20), default="auto")
    status = Column(String(20), default="CREATED")  # CREATED / UPLOADED / EXTRACTING / ROUTE_SET_READY / GENERATED / EXTRACT_ERROR
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    documents = relationship("Document", back_populates="project")
    references = relationship("Reference", back_populates="project")
    operations = relationship("Operation", back_populates="project")
    document_operation_details = relationship("DocumentOperationDetail", back_populates="project")
    generated_routes = relationship("GeneratedRoute", back_populates="project")
    param_rule_snapshots = relationship("ParamRuleSnapshot", back_populates="project")
    param_audit_answers = relationship("ParamAuditAnswer", back_populates="project")
    route_merge_snapshots = relationship("RouteMergeSnapshot", back_populates="project")
    normalized_route_versions = relationship("NormalizedRouteVersion", back_populates="project")
    normalized_route_segment_factor_reviews = relationship("NormalizedRouteSegmentFactorReview", back_populates="project")
    normalized_route_segment_rule_reviews = relationship("NormalizedRouteSegmentRuleReview", back_populates="project")
    finalized_rule_packages = relationship("FinalizedRulePackage", back_populates="project")


# ---------- 工艺规程文件 ----------
class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    filename = Column(String(255), nullable=False)
    original_name = Column(String(255), nullable=False)
    file_type = Column(String(20))  # pdf / docx / xlsx
    file_size = Column(Integer)
    uploader = Column(String(100), default="默认用户")
    status = Column(String(20), default="uploaded")  # uploaded / parsing / parsed / error
    created_at = Column(DateTime, default=utcnow)

    project = relationship("Project", back_populates="documents")
    references = relationship("Reference", back_populates="document")
    operation_details = relationship("DocumentOperationDetail", back_populates="document")


# ---------- 参考资料 ----------
class Reference(Base):
    __tablename__ = "references"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    title = Column(String(255), nullable=False)
    content = Column(Text)
    ref_type = Column(String(20), default="written")  # written / uploaded
    filename = Column(String(255))
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    project = relationship("Project", back_populates="references")
    document = relationship("Document", back_populates="references")


# ---------- 工序 ----------
class Operation(Base):
    __tablename__ = "operations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    name = Column(String(255), nullable=False)
    sequence = Column(Integer, default=0)
    chain = Column(String(50))
    op_type = Column(String(20), default="MAIN")  # MAIN / BRANCH
    description = Column(Text)
    source = Column(String(500))
    confidence = Column(String(20), default="STRONG")  # STRONG / WEAK
    created_at = Column(DateTime, default=utcnow)

    project = relationship("Project", back_populates="operations")
    factors = relationship("Factor", back_populates="operation")


# ---------- 影响因素 ----------
class Factor(Base):
    __tablename__ = "factors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    operation_id = Column(Integer, ForeignKey("operations.id"), nullable=False)
    name = Column(String(255), nullable=False)
    evidence = Column(Text)
    strength = Column(String(20), default="STRONG")  # STRONG / WEAK
    confirmed = Column(Boolean, default=False)
    confirmed_by = Column(String(100))
    confirmed_at = Column(DateTime)

    operation = relationship("Operation", back_populates="factors")


# ---------- 文档级工序明细 ----------
class DocumentOperationDetail(Base):
    __tablename__ = "document_operation_details"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=True)
    pdf_name = Column(String(255), nullable=False)
    operation_seq = Column(Integer, default=0)
    operation_name = Column(String(255), nullable=False)
    operation_content = Column(Text)
    page_no = Column(Integer)
    equipment_types = Column(Text)
    equipment_models = Column(Text)
    normalized_name = Column(String(255))
    is_composite = Column(Boolean, default=False)
    source_type = Column(String(50), default="pdf_table_extract")
    created_at = Column(DateTime, default=utcnow)

    project = relationship("Project", back_populates="document_operation_details")
    document = relationship("Document", back_populates="operation_details")


# ---------- 生成的工艺路线实例 ----------
class GeneratedRoute(Base):
    __tablename__ = "generated_routes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    input_factors = Column(Text)  # JSON string
    result_json = Column(Text)     # JSON string
    created_at = Column(DateTime, default=utcnow)
    modified = Column(Boolean, default=False)

    project = relationship("Project", back_populates="generated_routes")


# ---------- 参数到 JSON：规则引擎快照 ----------
class ParamRuleSnapshot(Base):
    __tablename__ = "param_rule_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    source_signature = Column(String(255))
    compile_mode = Column(String(20), default="heuristic")  # heuristic / llm
    summary = Column(Text)
    factor_schema_json = Column(Text)   # JSON string
    stage_template_json = Column(Text)  # JSON string
    compiled_rules_json = Column(Text)  # JSON string
    validation_report_json = Column(Text)  # JSON string
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    project = relationship("Project", back_populates="param_rule_snapshots")


# ---------- 参数到 JSON：第二步审核答案 ----------
class ParamAuditAnswer(Base):
    __tablename__ = "param_audit_answers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    operation_key = Column(String(255), nullable=False)
    stage = Column(String(100))
    occurrence_index = Column(Integer, default=1)
    step_name = Column(String(255))
    factor_key = Column(String(100), nullable=False)
    question_type = Column(String(100))
    selected_value = Column(String(255), nullable=False)
    selected_label = Column(String(255))
    answer_kind = Column(String(30), default="selected")  # selected / custom / unsure / data_issue
    note = Column(Text)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    project = relationship("Project", back_populates="param_audit_answers")


# ---------- route_rules：第二步归并快照 ----------
class RouteMergeSnapshot(Base):
    __tablename__ = "route_merge_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    source_signature = Column(String(255))
    superset_route_json = Column(Text)
    merge_groups_json = Column(Text)
    merge_suggestions_json = Column(Text)
    normalized_superset_route_json = Column(Text)
    review_state_json = Column(Text)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    project = relationship("Project", back_populates="route_merge_snapshots")


class NormalizedRouteVersion(Base):
    __tablename__ = "normalized_route_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    source_signature = Column(String(255))
    saved_by = Column(String(100), default="默认用户")
    total_docs = Column(Integer, default=0)
    segment_count = Column(Integer, default=0)
    route_json = Column(Text)
    created_at = Column(DateTime, default=utcnow)

    project = relationship("Project", back_populates="normalized_route_versions")
    factor_reviews = relationship("NormalizedRouteSegmentFactorReview", back_populates="route_version")
    rule_reviews = relationship("NormalizedRouteSegmentRuleReview", back_populates="route_version")


class NormalizedRouteSegmentFactorReview(Base):
    __tablename__ = "normalized_route_segment_factor_reviews"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    route_version_id = Column(Integer, ForeignKey("normalized_route_versions.id"), nullable=False)
    segment_id = Column(String(100), nullable=False)
    factor_name = Column(String(255), nullable=False)
    decision = Column(String(20), default="confirmed")  # confirmed / excluded
    note = Column(Text)
    source_type = Column(String(20), default="aggregated")  # aggregated / manual
    evidence_refs_json = Column(Text)
    source_operation_ids_json = Column(Text)
    source_operation_names_json = Column(Text)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    project = relationship("Project", back_populates="normalized_route_segment_factor_reviews")
    route_version = relationship("NormalizedRouteVersion", back_populates="factor_reviews")


class NormalizedRouteSegmentRuleReview(Base):
    __tablename__ = "normalized_route_segment_rule_reviews"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    route_version_id = Column(Integer, ForeignKey("normalized_route_versions.id"), nullable=False)
    segment_id = Column(String(100), nullable=False)
    decision = Column(String(20), default="accepted")  # accepted / rejected
    note = Column(Text)
    summary_json = Column(Text)
    question_trail_json = Column(Text)
    condition_source_text = Column(Text)
    condition_source_hash = Column(String(64))
    condition_status = Column(String(30), default="draft")
    condition_candidate_json = Column(Text)
    condition_confirmed_json = Column(Text)
    condition_confidence = Column(Float)
    condition_issues_json = Column(Text)
    condition_field_registry_version = Column(String(20))
    condition_confirmed_by = Column(String(100))
    condition_confirmed_at = Column(DateTime)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    project = relationship("Project", back_populates="normalized_route_segment_rule_reviews")
    route_version = relationship("NormalizedRouteVersion", back_populates="rule_reviews")


class FinalizedRulePackage(Base):
    __tablename__ = "finalized_rule_packages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    route_version_id = Column(Integer, ForeignKey("normalized_route_versions.id"), nullable=True)
    version = Column(Integer, nullable=False, default=1)
    package_name = Column(String(255), nullable=False)
    schema_version = Column(String(20), nullable=False, default="1.0")
    status = Column(String(20), nullable=False, default="published")
    manifest_json = Column(Text)
    input_schema_json = Column(Text)
    route_catalog_json = Column(Text)
    route_rules_json = Column(Text)
    test_cases_json = Column(Text)
    rule_report_md = Column(Text)
    validation_report_json = Column(Text)
    content_hash = Column(String(64))
    created_by = Column(String(100), default="默认用户")
    created_at = Column(DateTime, default=utcnow)
    published_by = Column(String(100))
    published_at = Column(DateTime)
    supersedes_id = Column(Integer, ForeignKey("finalized_rule_packages.id"), nullable=True)

    project = relationship("Project", back_populates="finalized_rule_packages")
