"""Durable external IDs; unrelated to executable core identity or workflow revision."""
from sqlalchemy import CheckConstraint, Column, ForeignKey, Integer, String, Text, UniqueConstraint

from app.database import Base


class PublicRulePackageIdentity(Base):
    __tablename__ = 'public_rule_package_identities'
    __table_args__ = (
        UniqueConstraint('project_id', 'kind', 'native_id', name='uq_public_identity_native'),
        UniqueConstraint('project_id', 'kind', 'ordinal', name='uq_public_identity_ordinal'),
        CheckConstraint("kind IN ('processes', 'steps', 'factors')", name='ck_public_identity_kind'),
        CheckConstraint('ordinal > 0', name='ck_public_identity_ordinal'),
    )

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True)
    kind = Column(String(12), nullable=False)
    native_id = Column(Text, nullable=False)
    ordinal = Column(Integer, nullable=False)
