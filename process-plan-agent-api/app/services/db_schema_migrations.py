from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from app.services.profile_registry import ROUTE_RULES_PROFILE


MigrationResult = dict[str, Any]
MigrationApply = Callable[[Any], Awaitable[MigrationResult | None]]


@dataclass(frozen=True)
class SchemaMigration:
    version: int
    name: str
    apply: MigrationApply


class DatabaseMigrationError(RuntimeError):
    def __init__(self, migration: SchemaMigration, cause: Exception):
        super().__init__(
            f"Database migration {migration.version} ({migration.name}) failed: {cause}"
        )
        self.version = migration.version
        self.migration_name = migration.name


def _validated_registry(
    migrations: Sequence[SchemaMigration],
) -> tuple[SchemaMigration, ...]:
    ordered = tuple(sorted(migrations, key=lambda item: item.version))
    versions = [migration.version for migration in ordered]
    names = [migration.name for migration in ordered]
    if any(version <= 0 for version in versions):
        raise ValueError("Database migration versions must be positive")
    if len(versions) != len(set(versions)):
        raise ValueError("Database migration versions must be unique")
    if any(not name.strip() for name in names):
        raise ValueError("Database migration names must not be empty")
    if len(names) != len(set(names)):
        raise ValueError("Database migration names must be unique")
    return ordered


async def _migration_table_columns(conn) -> set[str]:
    rows = (
        await conn.execute(text('PRAGMA table_info("schema_migrations")'))
    ).all()
    return {str(row[1]) for row in rows}


async def _bootstrap_migration_table(
    conn,
    registry: Sequence[SchemaMigration],
) -> None:
    await conn.execute(text("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            name VARCHAR(100) PRIMARY KEY,
            version INTEGER NOT NULL,
            applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            result_json TEXT NOT NULL
        )
    """))
    columns = await _migration_table_columns(conn)
    if "version" not in columns:
        await conn.execute(
            text("ALTER TABLE schema_migrations ADD COLUMN version INTEGER")
        )
    if "result_json" not in columns:
        await conn.execute(
            text("ALTER TABLE schema_migrations ADD COLUMN result_json TEXT")
        )

    expected_by_name = {migration.name: migration.version for migration in registry}
    legacy_name = "retire_kmai_factor_mappings_v1"
    if legacy_name in expected_by_name:
        await conn.execute(
            text("""
                UPDATE schema_migrations
                SET version = :version,
                    result_json = '{"status":"adopted_legacy_record"}'
                WHERE name = :name
                  AND version IS NULL
            """),
            {"name": legacy_name, "version": expected_by_name[legacy_name]},
        )

    history = (
        await conn.execute(text("""
            SELECT name, version, result_json
            FROM schema_migrations
            ORDER BY applied_at, name
        """))
    ).all()
    version_counts: dict[int, int] = {}
    for row in history:
        name = str(row.name)
        if name not in expected_by_name:
            raise RuntimeError(f"Unknown database migration history entry: {name}")
        if row.version is None:
            raise RuntimeError(f"Database migration history entry has no version: {name}")
        version = int(row.version)
        version_counts[version] = version_counts.get(version, 0) + 1

    for version, count in version_counts.items():
        if count > 1:
            raise RuntimeError(
                f"Database migration history contains duplicate version {version}"
            )

    for row in history:
        name = str(row.name)
        version = int(row.version)
        expected_version = expected_by_name[name]
        if version != expected_version:
            raise RuntimeError(
                f"Database migration history mismatch for {name}: "
                f"expected version {expected_version}, found {version}"
            )
        if row.result_json is None or not str(row.result_json).strip():
            raise RuntimeError(f"Database migration history entry has no result: {name}")

    await conn.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_schema_migrations_version
        ON schema_migrations (version)
    """))


async def run_schema_migrations(
    conn,
    *,
    migrations: Sequence[SchemaMigration] | None = None,
) -> None:
    registry = _validated_registry(
        SCHEMA_MIGRATIONS if migrations is None else migrations
    )
    savepoint = "processmind_schema_migrations"
    await conn.exec_driver_sql(f"SAVEPOINT {savepoint}")
    try:
        await _bootstrap_migration_table(conn, registry)
        applied_rows = (
            await conn.execute(text("SELECT version, name FROM schema_migrations"))
        ).all()
        applied = {int(row.version): str(row.name) for row in applied_rows}

        for migration in registry:
            applied_name = applied.get(migration.version)
            if applied_name is not None:
                if applied_name != migration.name:
                    raise RuntimeError(
                        "Database migration history mismatch for version "
                        f"{migration.version}: expected {migration.name}, found {applied_name}"
                    )
                continue
            try:
                result = await migration.apply(conn)
                payload = {**(result or {}), "status": "applied"}
                await conn.execute(
                    text("""
                        INSERT INTO schema_migrations (name, version, result_json)
                        VALUES (:name, :version, :result_json)
                    """),
                    {
                        "name": migration.name,
                        "version": migration.version,
                        "result_json": json.dumps(
                            payload,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                    },
                )
            except DatabaseMigrationError:
                raise
            except Exception as error:
                raise DatabaseMigrationError(migration, error) from error
    except Exception:
        await conn.exec_driver_sql(f"ROLLBACK TO SAVEPOINT {savepoint}")
        await conn.exec_driver_sql(f"RELEASE SAVEPOINT {savepoint}")
        raise
    else:
        await conn.exec_driver_sql(f"RELEASE SAVEPOINT {savepoint}")


async def _ensure_column(
    conn,
    table_name: str,
    column_name: str,
    ddl: str,
) -> bool:
    result = await conn.execute(text(f'PRAGMA table_info("{table_name}")'))
    columns = [str(row[1]) for row in result.fetchall()]
    if column_name in columns:
        return False
    await conn.execute(text(f'ALTER TABLE "{table_name}" ADD COLUMN {ddl}'))
    return True


async def _legacy_project_schema_v1(conn) -> MigrationResult:
    await conn.execute(text("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(255) NOT NULL,
            status VARCHAR(20) DEFAULT 'CREATED',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """))
    columns = (
        ("documents", "project_id", "project_id INTEGER"),
        ("references", "project_id", "project_id INTEGER"),
        ("operations", "project_id", "project_id INTEGER"),
        ("operations", "chain", "chain VARCHAR(50)"),
        (
            "document_operation_details",
            "equipment_types",
            "equipment_types TEXT",
        ),
        (
            "document_operation_details",
            "equipment_models",
            "equipment_models TEXT",
        ),
        ("generated_routes", "project_id", "project_id INTEGER"),
    )
    added = 0
    for table_name, column_name, ddl in columns:
        added += int(await _ensure_column(conn, table_name, column_name, ddl))
    return {"columns_added": added}


async def _backfill_chain_columns(conn) -> None:
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


async def _workflow_review_schema_v1(conn) -> MigrationResult:
    review_columns = (
        ("question_trail_json", "question_trail_json TEXT"),
        ("condition_source_text", "condition_source_text TEXT"),
        ("condition_source_hash", "condition_source_hash VARCHAR(64)"),
        (
            "condition_status",
            "condition_status VARCHAR(30) DEFAULT 'draft'",
        ),
        ("condition_candidate_json", "condition_candidate_json TEXT"),
        ("condition_confirmed_json", "condition_confirmed_json TEXT"),
        ("condition_confidence", "condition_confidence FLOAT"),
        ("condition_issues_json", "condition_issues_json TEXT"),
        (
            "condition_field_registry_version",
            "condition_field_registry_version VARCHAR(20)",
        ),
        ("condition_parser_version", "condition_parser_version VARCHAR(64)"),
        ("condition_parse_duration_ms", "condition_parse_duration_ms INTEGER"),
        ("condition_confirmed_by", "condition_confirmed_by VARCHAR(100)"),
        ("condition_confirmed_at", "condition_confirmed_at DATETIME"),
    )
    added = 0
    for column_name, ddl in review_columns:
        added += int(
            await _ensure_column(
                conn,
                "normalized_route_segment_rule_reviews",
                column_name,
                ddl,
            )
        )
    project_columns = (
        ("mode", "mode VARCHAR(50) DEFAULT 'route_rules'"),
        (
            "profile",
            f"profile VARCHAR(100) DEFAULT '{ROUTE_RULES_PROFILE}'",
        ),
        ("rule_engine", "rule_engine VARCHAR(20) DEFAULT 'auto'"),
        (
            "workflow_revision",
            "workflow_revision INTEGER NOT NULL DEFAULT 0",
        ),
    )
    for column_name, ddl in project_columns:
        added += int(await _ensure_column(conn, "projects", column_name, ddl))

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
    added += int(
        await _ensure_column(
            conn,
            "extraction_task_states",
            "force_reextract",
            "force_reextract BOOLEAN NOT NULL DEFAULT 0",
        )
    )

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
    await _backfill_chain_columns(conn)
    return {"columns_added": added}


async def _operation_identity_index(conn) -> tuple[int, str]:
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
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_operations_project_seq_name
            ON operations (project_id, sequence, name)
        """))
        return int(duplicate_count), "non_unique"
    await conn.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_operations_project_seq_name
        ON operations (project_id, sequence, name)
    """))
    return 0, "unique"


async def _route_review_indexes_v1(conn) -> MigrationResult:
    duplicate_count, identity_index = await _operation_identity_index(conn)
    statements = (
        """CREATE INDEX IF NOT EXISTS idx_doc_op_details_project_document
           ON document_operation_details (project_id, document_id)""",
        """CREATE INDEX IF NOT EXISTS idx_doc_op_details_project_name
           ON document_operation_details (project_id, operation_name)""",
        """CREATE INDEX IF NOT EXISTS idx_doc_op_details_project_seq
           ON document_operation_details (project_id, operation_seq)""",
        """CREATE INDEX IF NOT EXISTS idx_route_merge_snapshots_project
           ON route_merge_snapshots (project_id)""",
        """CREATE INDEX IF NOT EXISTS idx_normalized_route_versions_project
           ON normalized_route_versions (project_id, version DESC, id DESC)""",
        """CREATE UNIQUE INDEX IF NOT EXISTS uq_normalized_route_versions_project_version
           ON normalized_route_versions (project_id, version)""",
        """CREATE INDEX IF NOT EXISTS idx_route_segment_factor_reviews_project
           ON normalized_route_segment_factor_reviews
              (project_id, route_version_id, segment_id)""",
        """CREATE UNIQUE INDEX IF NOT EXISTS uq_route_segment_factor_reviews_segment_factor
           ON normalized_route_segment_factor_reviews
              (route_version_id, segment_id, factor_name)""",
        """CREATE INDEX IF NOT EXISTS idx_route_segment_rule_reviews_project
           ON normalized_route_segment_rule_reviews
              (project_id, route_version_id, segment_id)""",
        """CREATE UNIQUE INDEX IF NOT EXISTS uq_route_segment_rule_reviews_segment
           ON normalized_route_segment_rule_reviews (route_version_id, segment_id)""",
        """CREATE UNIQUE INDEX IF NOT EXISTS uq_param_audit_answers_project_op_factor
           ON param_audit_answers (project_id, operation_key, factor_key)""",
    )
    for statement in statements:
        await conn.execute(text(statement))
    return {
        "duplicate_operation_group_count": duplicate_count,
        "operation_identity_index": identity_index,
    }


async def _sqlite_table_names(conn) -> set[str]:
    rows = (
        await conn.execute(text("SELECT name FROM sqlite_master WHERE type = 'table'"))
    ).all()
    return {str(row[0]) for row in rows}


def _validated_usage_snapshots(rows) -> dict[int, list[dict]]:
    grouped: dict[int, list[dict]] = {}
    for row in rows:
        package_id = int(row["package_id"])
        if row["package_row_id"] is None:
            raise RuntimeError(
                f"KmAI mapping usage {row['usage_id']} references missing package {package_id}"
            )
        try:
            snapshot = json.loads(row["mapping_snapshot_json"])
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise RuntimeError(
                f"KmAI mapping usage {row['usage_id']} contains malformed snapshot JSON"
            ) from error
        if not isinstance(snapshot, dict):
            raise RuntimeError(
                f"KmAI mapping usage {row['usage_id']} snapshot must be a JSON object"
            )
        grouped.setdefault(package_id, []).append(snapshot)
    return grouped


def _validation_report_object(raw_report, package_id: int) -> dict:
    if raw_report is None or not str(raw_report).strip():
        return {}
    try:
        report = json.loads(raw_report)
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise RuntimeError(
            f"Finalized package {package_id} has malformed validation report JSON"
        ) from error
    if not isinstance(report, dict):
        raise RuntimeError(
            f"Finalized package {package_id} validation report must be a JSON object"
        )
    return report


async def _backfill_missing_package_snapshots(
    conn,
    grouped: dict[int, list[dict]],
) -> set[int]:
    backfilled: set[int] = set()
    for package_id, snapshots in grouped.items():
        raw_report = (
            await conn.execute(
                text(
                    "SELECT validation_report_json FROM finalized_rule_packages WHERE id = :id"
                ),
                {"id": package_id},
            )
        ).scalar_one()
        report = _validation_report_object(raw_report, package_id)
        compatibility = report.get("kmai_compatibility")
        if compatibility is None:
            compatibility = {}
            report["kmai_compatibility"] = compatibility
        if not isinstance(compatibility, dict):
            raise RuntimeError(
                f"Finalized package {package_id} KmAI compatibility report must be a JSON object"
            )
        if compatibility.get("mapping_snapshot"):
            continue
        compatibility["mapping_snapshot"] = snapshots
        await conn.execute(
            text("""
                UPDATE finalized_rule_packages
                SET validation_report_json = :validation_report_json
                WHERE id = :id
            """),
            {
                "id": package_id,
                "validation_report_json": json.dumps(
                    report,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            },
        )
        backfilled.add(package_id)
    return backfilled


async def _verify_package_snapshots(
    conn,
    grouped: dict[int, list[dict]],
    backfilled: set[int],
) -> None:
    for package_id in backfilled:
        raw_report = (
            await conn.execute(
                text(
                    "SELECT validation_report_json FROM finalized_rule_packages WHERE id = :id"
                ),
                {"id": package_id},
            )
        ).scalar_one()
        report = _validation_report_object(raw_report, package_id)
        compatibility = report.get("kmai_compatibility")
        actual = (
            compatibility.get("mapping_snapshot")
            if isinstance(compatibility, dict)
            else None
        )
        if not isinstance(actual, list) or not actual or actual != grouped[package_id]:
            raise RuntimeError(
                f"KmAI mapping snapshot verification failed for finalized package {package_id}"
            )


async def _retire_kmai_mapping_tables(conn) -> bool:
    table_names = await _sqlite_table_names(conn)
    legacy = {
        "kmai_factor_mapping_usages",
        "kmai_factor_mapping_events",
        "kmai_factor_mappings",
    }
    if not (legacy & table_names):
        return False
    if not legacy <= table_names:
        raise RuntimeError(
            "KmAI mapping tables are only partially present; refusing destructive cleanup"
        )

    rows = (
        await conn.execute(text("""
            SELECT usage.id AS usage_id,
                   usage.package_id,
                   usage.mapping_snapshot_json,
                   package.id AS package_row_id
            FROM kmai_factor_mapping_usages AS usage
            LEFT JOIN finalized_rule_packages AS package ON package.id = usage.package_id
            ORDER BY usage.package_id, usage.id
        """))
    ).mappings().all()
    grouped = _validated_usage_snapshots(rows)
    backfilled = await _backfill_missing_package_snapshots(conn, grouped)
    await _verify_package_snapshots(conn, grouped, backfilled)
    await conn.execute(text("DROP TABLE kmai_factor_mapping_usages"))
    await conn.execute(text("DROP TABLE kmai_factor_mapping_events"))
    await conn.execute(text("DROP TABLE kmai_factor_mappings"))
    return True


async def _backfill_rule_package_hashes(conn) -> int:
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
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        content_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        await conn.execute(
            text(
                "UPDATE finalized_rule_packages "
                "SET content_hash = :content_hash WHERE id = :id"
            ),
            {"content_hash": content_hash, "id": row["id"]},
        )
    return len(rows)


async def _normalize_published_rule_packages(conn) -> int:
    rows = (
        await conn.execute(text("""
            SELECT project_id, id
            FROM finalized_rule_packages
            WHERE status = 'published'
            ORDER BY project_id ASC, version DESC, id DESC
        """))
    ).all()
    seen_projects: set[int] = set()
    normalized = 0
    for project_id, package_id in rows:
        if project_id in seen_projects:
            await conn.execute(
                text(
                    "UPDATE finalized_rule_packages "
                    "SET status = 'superseded' WHERE id = :id"
                ),
                {"id": package_id},
            )
            normalized += 1
        else:
            seen_projects.add(project_id)
    return normalized


async def _rule_package_lifecycle_v2(conn) -> MigrationResult:

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

    status_added = await _ensure_column(
        conn,
        "finalized_rule_packages",
        "status",
        "status VARCHAR(20) NOT NULL DEFAULT 'published'",
    )
    columns = (
        ("schema_version", "schema_version VARCHAR(20) NOT NULL DEFAULT '1.0'"),
        ("manifest_json", "manifest_json TEXT"),
        ("test_cases_json", "test_cases_json TEXT"),
        ("content_hash", "content_hash VARCHAR(64)"),
        ("published_by", "published_by VARCHAR(100)"),
        ("published_at", "published_at DATETIME"),
        ("supersedes_id", "supersedes_id INTEGER"),
    )
    added = int(status_added)
    for column_name, ddl in columns:
        added += int(
            await _ensure_column(
                conn,
                "finalized_rule_packages",
                column_name,
                ddl,
            )
        )

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

    hashes_backfilled = await _backfill_rule_package_hashes(conn)
    packages_normalized = await _normalize_published_rule_packages(conn)
    await conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_finalized_rule_packages_project_status
        ON finalized_rule_packages (project_id, status, version DESC, id DESC)
    """))
    await conn.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_rule_package_project_published
        ON finalized_rule_packages (project_id)
        WHERE status = 'published'
    """))
    return {
        "columns_added": added,
        "hashes_backfilled": hashes_backfilled,
        "packages_normalized": packages_normalized,
        "status_column_added": status_added,
    }


async def _retire_kmai_factor_mappings_v1(conn) -> MigrationResult:
    retired = await _retire_kmai_mapping_tables(conn)
    return {"legacy_tables_retired": retired}


SCHEMA_MIGRATIONS: tuple[SchemaMigration, ...] = (
    SchemaMigration(1, "legacy_project_schema_v1", _legacy_project_schema_v1),
    SchemaMigration(2, "workflow_review_schema_v1", _workflow_review_schema_v1),
    SchemaMigration(3, "route_review_indexes_v1", _route_review_indexes_v1),
    SchemaMigration(4, "rule_package_lifecycle_v2", _rule_package_lifecycle_v2),
    SchemaMigration(
        5,
        "retire_kmai_factor_mappings_v1",
        _retire_kmai_factor_mappings_v1,
    ),
)


async def ensure_project_schema(conn) -> None:
    await run_schema_migrations(conn)
