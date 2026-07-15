import hashlib
import json

from sqlalchemy import text

from app.services.profile_registry import ROUTE_RULES_PROFILE


async def ensure_project_schema(conn):
    await conn.execute(text("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(255) NOT NULL,
            status VARCHAR(20) DEFAULT 'CREATED',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """))

    async def ensure_column(table_name: str, column_name: str, ddl: str):
        result = await conn.execute(text(f'PRAGMA table_info("{table_name}")'))
        columns = [row[1] for row in result.fetchall()]
        if column_name not in columns:
            await conn.execute(text(f'ALTER TABLE "{table_name}" ADD COLUMN {ddl}'))
            return True
        return False

    await ensure_column("documents", "project_id", "project_id INTEGER")
    await ensure_column("references", "project_id", "project_id INTEGER")
    await ensure_column("operations", "project_id", "project_id INTEGER")
    await ensure_column("operations", "chain", "chain VARCHAR(50)")
    await ensure_column("document_operation_details", "equipment_types", "equipment_types TEXT")
    await ensure_column("document_operation_details", "equipment_models", "equipment_models TEXT")
    await ensure_column("generated_routes", "project_id", "project_id INTEGER")
    await ensure_column("normalized_route_segment_rule_reviews", "question_trail_json", "question_trail_json TEXT")
    await ensure_column("projects", "mode", "mode VARCHAR(50) DEFAULT 'route_rules'")
    await ensure_column("projects", "profile", f"profile VARCHAR(100) DEFAULT '{ROUTE_RULES_PROFILE}'")
    await ensure_column("projects", "rule_engine", "rule_engine VARCHAR(20) DEFAULT 'auto'")

    await conn.execute(text(f"""
        UPDATE projects
        SET created_at = COALESCE(created_at, CURRENT_TIMESTAMP),
            updated_at = COALESCE(updated_at, CURRENT_TIMESTAMP),
            mode = 'route_rules',
            profile = '{ROUTE_RULES_PROFILE}'
        WHERE created_at IS NULL OR updated_at IS NULL
    """))
    await conn.execute(text("""
        UPDATE projects
        SET mode = 'route_rules'
        WHERE mode IS NULL OR TRIM(mode) = ''
    """))
    await conn.execute(text(f"""
        UPDATE projects
        SET profile = '{ROUTE_RULES_PROFILE}'
        WHERE profile IS NULL
           OR TRIM(profile) = ''
           OR profile NOT LIKE 'route_rules.%'
    """))
    await conn.execute(text("""
        UPDATE projects
        SET rule_engine = 'auto'
        WHERE rule_engine IS NULL
           OR TRIM(rule_engine) = ''
           OR rule_engine NOT IN ('auto', 'v1', 'v2')
    """))
    await conn.execute(text("""
        UPDATE projects
        SET status = 'ROUTE_SET_READY'
        WHERE status IN ('BUILDING_RULE_ASSETS', 'RULE_ASSETS_READY', 'EXTRACTED')
    """))

    await backfill_chain_columns(conn)
    await dedupe_operations(conn)
    await conn.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_operations_project_seq_name
        ON operations (project_id, sequence, name)
    """))
    await conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_doc_op_details_project_document
        ON document_operation_details (project_id, document_id)
    """))
    await conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_doc_op_details_project_name
        ON document_operation_details (project_id, operation_name)
    """))
    await conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_doc_op_details_project_seq
        ON document_operation_details (project_id, operation_seq)
    """))
    await conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_route_merge_snapshots_project
        ON route_merge_snapshots (project_id)
    """))
    await conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_normalized_route_versions_project
        ON normalized_route_versions (project_id, version DESC, id DESC)
    """))
    await conn.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_normalized_route_versions_project_version
        ON normalized_route_versions (project_id, version)
    """))
    await conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_route_segment_factor_reviews_project
        ON normalized_route_segment_factor_reviews (project_id, route_version_id, segment_id)
    """))
    await conn.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_route_segment_factor_reviews_segment_factor
        ON normalized_route_segment_factor_reviews (route_version_id, segment_id, factor_name)
    """))
    await conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_route_segment_rule_reviews_project
        ON normalized_route_segment_rule_reviews (project_id, route_version_id, segment_id)
    """))
    await conn.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_route_segment_rule_reviews_segment
        ON normalized_route_segment_rule_reviews (route_version_id, segment_id)
    """))
    await conn.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_param_audit_answers_project_op_factor
        ON param_audit_answers (project_id, operation_key, factor_key)
    """))
    await conn.execute(text("""
        CREATE TABLE IF NOT EXISTS finalized_rule_packages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            route_version_id INTEGER,
            version INTEGER NOT NULL DEFAULT 1,
            package_name VARCHAR(255) NOT NULL,
            input_schema_json TEXT,
            route_catalog_json TEXT,
            route_rules_json TEXT,
            rule_report_md TEXT,
            validation_report_json TEXT,
            created_by VARCHAR(100) DEFAULT '默认用户',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """))
    await conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_finalized_rule_packages_project
        ON finalized_rule_packages (project_id, version DESC, id DESC)
    """))
    await conn.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_finalized_rule_packages_project_version
        ON finalized_rule_packages (project_id, version)
    """))

    status_added = await ensure_column(
        "finalized_rule_packages",
        "status",
        "status VARCHAR(20) NOT NULL DEFAULT 'published'",
    )
    await ensure_column(
        "finalized_rule_packages",
        "schema_version",
        "schema_version VARCHAR(20) NOT NULL DEFAULT '1.0'",
    )
    await ensure_column("finalized_rule_packages", "manifest_json", "manifest_json TEXT")
    await ensure_column("finalized_rule_packages", "test_cases_json", "test_cases_json TEXT")
    await ensure_column("finalized_rule_packages", "content_hash", "content_hash VARCHAR(64)")
    await ensure_column("finalized_rule_packages", "published_by", "published_by VARCHAR(100)")
    await ensure_column("finalized_rule_packages", "published_at", "published_at DATETIME")
    await ensure_column("finalized_rule_packages", "supersedes_id", "supersedes_id INTEGER")

    if status_added:
        await conn.execute(text("""
            UPDATE finalized_rule_packages
            SET status = 'superseded',
                schema_version = COALESCE(NULLIF(TRIM(schema_version), ''), '1.0'),
                published_at = COALESCE(published_at, created_at)
        """))
        await conn.execute(text("""
            UPDATE finalized_rule_packages
            SET status = 'published'
            WHERE id IN (
                SELECT id
                FROM finalized_rule_packages AS candidate
                WHERE candidate.id = (
                    SELECT latest.id
                    FROM finalized_rule_packages AS latest
                    WHERE latest.project_id = candidate.project_id
                    ORDER BY latest.version DESC, latest.id DESC
                    LIMIT 1
                )
            )
        """))

    await _backfill_rule_package_hashes(conn)
    await _normalize_published_rule_packages(conn)
    await conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_finalized_rule_packages_project_status
        ON finalized_rule_packages (project_id, status, version DESC, id DESC)
    """))
    await conn.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_rule_package_project_published
        ON finalized_rule_packages (project_id)
        WHERE status = 'published'
    """))


async def _backfill_rule_package_hashes(conn):
    rows = (
        await conn.execute(text("""
            SELECT id, schema_version, package_name, manifest_json, input_schema_json,
                   route_catalog_json, route_rules_json, test_cases_json, rule_report_md
            FROM finalized_rule_packages
            WHERE content_hash IS NULL OR TRIM(content_hash) = ''
        """))
    ).mappings().all()
    for row in rows:
        payload = {
            "schema_version": row["schema_version"] or "1.0",
            "package_name": row["package_name"] or "",
            "manifest": row["manifest_json"] or "",
            "input_schema": row["input_schema_json"] or "",
            "route_catalog": row["route_catalog_json"] or "",
            "route_rules": row["route_rules_json"] or "",
            "test_cases": row["test_cases_json"] or "",
            "rule_report": row["rule_report_md"] or "",
        }
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        content_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        await conn.execute(
            text("UPDATE finalized_rule_packages SET content_hash = :content_hash WHERE id = :id"),
            {"content_hash": content_hash, "id": row["id"]},
        )


async def _normalize_published_rule_packages(conn):
    rows = (
        await conn.execute(text("""
            SELECT project_id, id
            FROM finalized_rule_packages
            WHERE status = 'published'
            ORDER BY project_id ASC, version DESC, id DESC
        """))
    ).all()
    seen_projects: set[int] = set()
    for project_id, package_id in rows:
        if project_id in seen_projects:
            await conn.execute(
                text("UPDATE finalized_rule_packages SET status = 'superseded' WHERE id = :id"),
                {"id": package_id},
            )
        else:
            seen_projects.add(project_id)


async def dedupe_operations(conn):
    await conn.execute(text("""
        DELETE FROM factors
        WHERE operation_id IN (
            SELECT dup.id
            FROM operations AS dup
            JOIN operations AS keep
              ON keep.project_id = dup.project_id
             AND keep.sequence = dup.sequence
             AND keep.name = dup.name
             AND keep.id < dup.id
        )
    """))
    await conn.execute(text("""
        DELETE FROM operations
        WHERE id IN (
            SELECT dup.id
            FROM operations AS dup
            JOIN operations AS keep
              ON keep.project_id = dup.project_id
             AND keep.sequence = dup.sequence
             AND keep.name = dup.name
             AND keep.id < dup.id
        )
    """))


async def backfill_chain_columns(conn):
    chain_case = """
        CASE
            WHEN COALESCE(name, '') LIKE '%淬火%'
              OR COALESCE(name, '') LIKE '%调质%'
              OR COALESCE(name, '') LIKE '%正常化%'
              OR COALESCE(name, '') LIKE '%回火%'
              OR COALESCE(name, '') LIKE '%热处理%'
              OR COALESCE(name, '') LIKE '%去应力%' THEN 'heat'
            WHEN COALESCE(name, '') LIKE '%磁粉%'
              OR COALESCE(name, '') LIKE '%烧伤%'
              OR COALESCE(name, '') LIKE '%外观检查%'
              OR COALESCE(name, '') LIKE '%检验%'
              OR COALESCE(name, '') LIKE '%探伤%' THEN 'inspection'
            WHEN COALESCE(name, '') LIKE '%磨孔%'
              OR COALESCE(name, '') LIKE '%研孔%'
              OR COALESCE(name, '') LIKE '%钻孔%'
              OR COALESCE(name, '') LIKE '%镗孔%'
              OR COALESCE(name, '') LIKE '%钻铰孔%'
              OR COALESCE(name, '') LIKE '%攻螺纹%'
              OR COALESCE(name, '') LIKE '%通孔%'
              OR COALESCE(name, '') LIKE '%孔%' THEN 'hole'
            WHEN COALESCE(name, '') LIKE '%铣扁%'
              OR COALESCE(name, '') LIKE '%铣槽%'
              OR COALESCE(name, '') LIKE '%花键%'
              OR COALESCE(name, '') LIKE '%键槽%'
              OR COALESCE(name, '') LIKE '%铣%'
              OR COALESCE(name, '') LIKE '%槽%'
              OR COALESCE(name, '') LIKE '%扁%' THEN 'feature'
            WHEN COALESCE(name, '') LIKE '%清洗%'
              OR COALESCE(name, '') LIKE '%去毛刺%'
              OR COALESCE(name, '') LIKE '%包装%'
              OR COALESCE(name, '') LIKE '%标印%' THEN 'release'
            WHEN COALESCE(name, '') LIKE '%磨外圆%'
              OR COALESCE(name, '') LIKE '%车外形%'
              OR COALESCE(name, '') LIKE '%车零件%'
              OR COALESCE(name, '') LIKE '%倒角%'
              OR COALESCE(name, '') LIKE '%磨外%'
              OR COALESCE(name, '') LIKE '%精车%'
              OR COALESCE(name, '') LIKE '%粗车%'
              OR COALESCE(name, '') LIKE '%外圆%'
              OR COALESCE(name, '') LIKE '%下料%' THEN 'shape'
            ELSE 'other'
        END
    """
    await conn.execute(text(f"""
        UPDATE operations
        SET chain = {chain_case}
    """))
