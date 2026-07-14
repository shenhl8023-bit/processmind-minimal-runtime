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
