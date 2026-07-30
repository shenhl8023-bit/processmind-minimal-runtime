import hashlib
import json
import logging

from sqlalchemy import text

from app.services.profile_registry import ROUTE_RULES_PROFILE

logger = logging.getLogger(__name__)


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
    await ensure_column("normalized_route_segment_rule_reviews", "condition_source_text", "condition_source_text TEXT")
    await ensure_column("normalized_route_segment_rule_reviews", "condition_source_hash", "condition_source_hash VARCHAR(64)")
    await ensure_column("normalized_route_segment_rule_reviews", "condition_status", "condition_status VARCHAR(30) DEFAULT 'draft'")
    await ensure_column("normalized_route_segment_rule_reviews", "condition_candidate_json", "condition_candidate_json TEXT")
    await ensure_column("normalized_route_segment_rule_reviews", "condition_confirmed_json", "condition_confirmed_json TEXT")
    await ensure_column("normalized_route_segment_rule_reviews", "condition_confidence", "condition_confidence FLOAT")
    await ensure_column("normalized_route_segment_rule_reviews", "condition_issues_json", "condition_issues_json TEXT")
    await ensure_column("normalized_route_segment_rule_reviews", "condition_field_registry_version", "condition_field_registry_version VARCHAR(20)")
    await ensure_column("normalized_route_segment_rule_reviews", "condition_parser_version", "condition_parser_version VARCHAR(64)")
    await ensure_column("normalized_route_segment_rule_reviews", "condition_parse_duration_ms", "condition_parse_duration_ms INTEGER")
    await ensure_column("normalized_route_segment_rule_reviews", "condition_confirmed_by", "condition_confirmed_by VARCHAR(100)")
    await ensure_column("normalized_route_segment_rule_reviews", "condition_confirmed_at", "condition_confirmed_at DATETIME")
    await ensure_column("projects", "mode", "mode VARCHAR(50) DEFAULT 'route_rules'")
    await ensure_column("projects", "profile", f"profile VARCHAR(100) DEFAULT '{ROUTE_RULES_PROFILE}'")
    await ensure_column("projects", "rule_engine", "rule_engine VARCHAR(20) DEFAULT 'auto'")
    await ensure_column("projects", "workflow_revision", "workflow_revision INTEGER NOT NULL DEFAULT 0")
    await conn.execute(text("""
        CREATE TABLE IF NOT EXISTS project_group_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL UNIQUE,
            original_filename VARCHAR(255) NOT NULL,
            source_encoding VARCHAR(32) NOT NULL,
            part_filename VARCHAR(255) NOT NULL,
            content_hash VARCHAR(64) NOT NULL,
            feature_dictionary_version VARCHAR(64) NOT NULL,
            source_xml TEXT NOT NULL,
            tree_json TEXT NOT NULL,
            validation_json TEXT NOT NULL DEFAULT '[]',
            mappings_json TEXT NOT NULL DEFAULT '[]',
            template_revision INTEGER NOT NULL DEFAULT 1,
            group_count INTEGER NOT NULL DEFAULT 0,
            feature_selection_count INTEGER NOT NULL DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
    """))
    await conn.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_project_group_templates_project
        ON project_group_templates(project_id)
    """))
    await conn.execute(text("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            name VARCHAR(100) PRIMARY KEY,
            applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """))
    await conn.execute(text("""
        CREATE TABLE IF NOT EXISTS schema_maintenance_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            migration_name VARCHAR(100) NOT NULL,
            status VARCHAR(30) NOT NULL,
            summary_json TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """))
    await conn.execute(text("""
        CREATE TABLE IF NOT EXISTS extraction_task_states (
            project_id INTEGER PRIMARY KEY,
            task_status VARCHAR(30) NOT NULL DEFAULT 'idle',
            stage VARCHAR(100) NOT NULL DEFAULT 'idle',
            message TEXT,
            error TEXT,
            progress INTEGER NOT NULL DEFAULT 0,
            started_at VARCHAR(64),
            updated_at VARCHAR(64),
            finished_at VARCHAR(64),
            project_status VARCHAR(30),
            harness_json TEXT,
            force_reextract BOOLEAN NOT NULL DEFAULT 0,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
    """))
    await ensure_column("extraction_task_states", "force_reextract", "force_reextract BOOLEAN NOT NULL DEFAULT 0")

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
        SET workflow_revision = 0
        WHERE workflow_revision IS NULL
    """))
    await conn.execute(text("""
        UPDATE projects
        SET status = 'ROUTE_SET_READY'
        WHERE status IN ('BUILDING_RULE_ASSETS', 'RULE_ASSETS_READY', 'EXTRACTED')
    """))

    # Older SQLite databases may reuse a deleted project's row id. Keep a
    # monotonic allocator so project-scoped caches cannot collide after a
    # project is deleted and recreated.
    await conn.execute(text("""
        CREATE TABLE IF NOT EXISTS project_id_sequence (
            id INTEGER PRIMARY KEY AUTOINCREMENT
        )
    """))
    current_max_project_id = (
        await conn.execute(text("SELECT COALESCE(MAX(id), 0) FROM projects"))
    ).scalar_one()
    sequence_max_id = (
        await conn.execute(text("SELECT COALESCE(MAX(id), 0) FROM project_id_sequence"))
    ).scalar_one()
    if current_max_project_id > sequence_max_id:
        await conn.execute(
            text("INSERT INTO project_id_sequence (id) VALUES (:project_id)"),
            {"project_id": current_max_project_id},
        )

    await backfill_chain_columns(conn)
    await audit_duplicate_operations(conn)
    await ensure_operations_project_seq_name_index(conn)
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
    # Mapping tables are maintained explicitly because deployed SQLite files
    # predate these ORM models. Each statement is safe on repeated startup.
    await conn.execute(text("""
        CREATE TABLE IF NOT EXISTS kmai_factor_mappings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope VARCHAR(16) NOT NULL CHECK (scope IN ('global', 'project')),
            project_id INTEGER,
            source_field VARCHAR(120) NOT NULL,
            source_value VARCHAR(255) NOT NULL,
            mapping_mode VARCHAR(24) NOT NULL CHECK (mapping_mode IN ('existing_factor', 'manual_factor')),
            target_factor_key VARCHAR(120) NOT NULL,
            target_factor_name VARCHAR(255) NOT NULL,
            target_factor_category VARCHAR(120) NOT NULL,
            status VARCHAR(16) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
            revision INTEGER NOT NULL DEFAULT 1,
            promoted_from_id INTEGER,
            created_by VARCHAR(100) NOT NULL DEFAULT '默认用户',
            updated_by VARCHAR(100) NOT NULL DEFAULT '默认用户',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY(promoted_from_id) REFERENCES kmai_factor_mappings(id) ON DELETE SET NULL,
            CHECK ((scope = 'global' AND project_id IS NULL) OR (scope = 'project' AND project_id IS NOT NULL))
        )
    """))
    await conn.execute(text("""
        CREATE TABLE IF NOT EXISTS kmai_factor_mapping_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mapping_id INTEGER,
            project_id INTEGER,
            action VARCHAR(40) NOT NULL,
            actor VARCHAR(100) NOT NULL DEFAULT '默认用户',
            before_json TEXT,
            after_json TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(mapping_id) REFERENCES kmai_factor_mappings(id) ON DELETE SET NULL,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
    """))
    await conn.execute(text("""
        CREATE TABLE IF NOT EXISTS kmai_factor_mapping_usages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mapping_id INTEGER,
            package_id INTEGER NOT NULL,
            revision INTEGER NOT NULL DEFAULT 1,
            mapping_snapshot_json TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(mapping_id) REFERENCES kmai_factor_mappings(id) ON DELETE RESTRICT,
            FOREIGN KEY(package_id) REFERENCES finalized_rule_packages(id) ON DELETE CASCADE
        )
    """))
    await _migrate_kmai_mapping_usage_mapping_id_nullable(conn)
    await conn.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_kmai_factor_mappings_global_source
        ON kmai_factor_mappings (source_field, source_value)
        WHERE scope = 'global' AND project_id IS NULL
    """))
    await conn.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_kmai_factor_mappings_project_source
        ON kmai_factor_mappings (project_id, source_field, source_value)
        WHERE scope = 'project' AND project_id IS NOT NULL
    """))
    await conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_kmai_factor_mappings_project_status
        ON kmai_factor_mappings (project_id, status)
    """))
    await conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_kmai_factor_mapping_events_mapping
        ON kmai_factor_mapping_events (mapping_id)
    """))
    await conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_kmai_factor_mapping_events_project
        ON kmai_factor_mapping_events (project_id)
    """))
    await conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_kmai_factor_mapping_usages_package
        ON kmai_factor_mapping_usages (package_id)
    """))
    await conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_kmai_factor_mapping_usages_mapping
        ON kmai_factor_mapping_usages (mapping_id)
    """))


async def _migrate_kmai_mapping_usage_mapping_id_nullable(conn):
    columns = (
        await conn.execute(text("PRAGMA table_info(kmai_factor_mapping_usages)"))
    ).all()
    mapping_id = next((column for column in columns if column[1] == "mapping_id"), None)
    if mapping_id is None or mapping_id[3] == 0:
        return

    await conn.execute(text("""
        CREATE TABLE kmai_factor_mapping_usages_rebuilt (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mapping_id INTEGER,
            package_id INTEGER NOT NULL,
            revision INTEGER NOT NULL DEFAULT 1,
            mapping_snapshot_json TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(mapping_id) REFERENCES kmai_factor_mappings(id) ON DELETE RESTRICT,
            FOREIGN KEY(package_id) REFERENCES finalized_rule_packages(id) ON DELETE CASCADE
        )
    """))
    await conn.execute(text("""
        INSERT INTO kmai_factor_mapping_usages_rebuilt
        (id, mapping_id, package_id, revision, mapping_snapshot_json, created_at)
        SELECT id, mapping_id, package_id, revision, mapping_snapshot_json, created_at
        FROM kmai_factor_mapping_usages
    """))
    await conn.execute(text("DROP TABLE kmai_factor_mapping_usages"))
    await conn.execute(text("""
        ALTER TABLE kmai_factor_mapping_usages_rebuilt
        RENAME TO kmai_factor_mapping_usages
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
    """Merge duplicate operation factors before deleting duplicate operation rows.

    This function is intentionally not called during normal application startup.
    It remains available for explicit maintenance scripts that can take backups
    and review the affected rows first.
    """
    duplicate_factor_rows = (
        await conn.execute(text("""
            SELECT dup.id AS duplicate_id, keep.id AS keep_id
            FROM operations AS dup
            JOIN operations AS keep
              ON keep.project_id = dup.project_id
             AND keep.sequence = dup.sequence
             AND keep.name = dup.name
             AND keep.id < dup.id
        """))
    ).mappings().all()
    for row in duplicate_factor_rows:
        await conn.execute(
            text("UPDATE factors SET operation_id = :keep_id WHERE operation_id = :duplicate_id"),
            {"keep_id": row["keep_id"], "duplicate_id": row["duplicate_id"]},
        )
    await conn.execute(text("""
        DELETE FROM factors
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM factors
            GROUP BY operation_id, name, COALESCE(evidence, ''), COALESCE(strength, ''), COALESCE(confirmed, 0)
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
        WHERE chain IS NULL OR TRIM(chain) = ''
    """))


async def ensure_operations_project_seq_name_index(conn):
    duplicate_count = (
        await conn.execute(text("""
            SELECT COUNT(*)
            FROM (
                SELECT project_id, sequence, name
                FROM operations
                GROUP BY project_id, sequence, name
                HAVING COUNT(*) > 1
            ) AS duplicate_groups
        """))
    ).scalar_one()
    if duplicate_count:
        logger.warning(
            "Skipped unique operations(project_id, sequence, name) index because %s duplicate groups exist.",
            duplicate_count,
        )
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_operations_project_seq_name
            ON operations (project_id, sequence, name)
        """))
        return
    await conn.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_operations_project_seq_name
        ON operations (project_id, sequence, name)
    """))


async def audit_duplicate_operations(conn):
    duplicate_groups = (
        await conn.execute(text("""
            SELECT project_id, sequence, name, COUNT(*) AS duplicate_count,
                   GROUP_CONCAT(id) AS operation_ids
            FROM operations
            GROUP BY project_id, sequence, name
            HAVING COUNT(*) > 1
        """))
    ).mappings().all()
    params = {
        "migration_name": "operations_identity_duplicates_audit_v1",
        "status": "needs_manual_review" if duplicate_groups else "ok",
        "summary_json": json.dumps(
            {
                "duplicate_group_count": len(duplicate_groups),
                "duplicate_groups": [dict(row) for row in duplicate_groups],
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
    }
    existing_count = (
        await conn.execute(
            text("""
                SELECT COUNT(*)
                FROM schema_maintenance_audit
                WHERE migration_name = :migration_name
            """),
            {"migration_name": params["migration_name"]},
        )
    ).scalar_one()
    if existing_count:
        await conn.execute(
            text("""
                UPDATE schema_maintenance_audit
                SET status = :status,
                    summary_json = :summary_json,
                    created_at = CURRENT_TIMESTAMP
                WHERE migration_name = :migration_name
            """),
            params,
        )
        return
    await conn.execute(
        text("""
            INSERT INTO schema_maintenance_audit (migration_name, status, summary_json)
            VALUES (:migration_name, :status, :summary_json)
        """),
        params,
    )
