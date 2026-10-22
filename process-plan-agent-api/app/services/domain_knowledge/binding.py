"""Explicit project pins; new global versions never move a project automatically."""
import json
from fastapi import HTTPException
from sqlalchemy import select
from app.models.models import Project
from .packages import get_package_version, package_ref


async def project_binding(db, project_id):
    project = await db.get(Project, project_id)
    if not project: raise HTTPException(404, '项目不存在')
    row = None
    if project.domain_knowledge_package_id:
        row = await get_package_version(db, project.domain_knowledge_package_id, project.domain_knowledge_package_version)
    return project, row


def binding_payload(project, row):
    return {'project_id': project.id, 'knowledge_package': package_ref(row) if row else None,
            'part_family': project.domain_part_family or '', 'material': project.domain_material or '',
            'stage': project.domain_stage or '', 'analysis_stale': bool(project.domain_analysis_stale),
            'workflow_revision': project.workflow_revision}


async def set_project_domain_knowledge_package(db, project_id, package_id, version, *, part_family='', material='', stage=''):
    project, old = await project_binding(db, project_id)
    row = await get_package_version(db, package_id, version) if package_id else None
    if row and row.status != 'active': raise HTTPException(409, '仅可选择已启用知识包')
    changed = ((package_ref(old) if old else None) != (package_ref(row) if row else None) or
               (project.domain_part_family or '', project.domain_material or '', project.domain_stage or '') != (part_family, material, stage))
    project.domain_knowledge_package_id = row.package_id if row else None
    project.domain_knowledge_package_version = row.version if row else None
    project.domain_part_family, project.domain_material, project.domain_stage = part_family, material, stage
    if changed:
        project.domain_analysis_stale = True
        project.workflow_revision += 1
    await db.commit()
    return binding_payload(project, row)
