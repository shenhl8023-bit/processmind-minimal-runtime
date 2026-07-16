#!/usr/bin/env python3
"""Collapse duplicate normalized_route_versions that share identical route content.

For each project:
1. Group rows by canonical content hash of route_json
2. Keep the latest row per hash; remount FK references from discarded rows
3. Delete discarded rows
4. Renumber remaining versions to 1..N by created_at / version / id

Usage:
  python scripts/cleanup_duplicate_route_versions.py
  python scripts/cleanup_duplicate_route_versions.py --db data/db/process_mind.db --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


def canonical_route_hash(route_json: str | None) -> str:
    try:
        payload = json.loads(route_json or "[]")
    except Exception:
        payload = []
    if not isinstance(payload, list):
        payload = []
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def fetch_versions(cur: sqlite3.Cursor) -> list[sqlite3.Row]:
    return list(
        cur.execute(
            """
            SELECT id, project_id, version, segment_count, total_docs,
                   source_signature, route_json, created_at
            FROM normalized_route_versions
            ORDER BY project_id, version, id
            """
        )
    )


def remount_rule_reviews(cur: sqlite3.Cursor, old_id: int, keep_id: int) -> dict[str, int]:
    moved = deleted = 0
    rows = list(
        cur.execute(
            """
            SELECT id, segment_id, updated_at
            FROM normalized_route_segment_rule_reviews
            WHERE route_version_id = ?
            ORDER BY updated_at DESC, id DESC
            """,
            (old_id,),
        )
    )
    for row in rows:
        existing = cur.execute(
            """
            SELECT id, updated_at
            FROM normalized_route_segment_rule_reviews
            WHERE route_version_id = ? AND segment_id = ?
            """,
            (keep_id, row["segment_id"]),
        ).fetchone()
        if existing:
            keep_ts = str(existing["updated_at"] or "")
            old_ts = str(row["updated_at"] or "")
            if old_ts > keep_ts:
                cur.execute(
                    "DELETE FROM normalized_route_segment_rule_reviews WHERE id = ?",
                    (existing["id"],),
                )
                cur.execute(
                    "UPDATE normalized_route_segment_rule_reviews SET route_version_id = ? WHERE id = ?",
                    (keep_id, row["id"]),
                )
                moved += 1
            else:
                cur.execute(
                    "DELETE FROM normalized_route_segment_rule_reviews WHERE id = ?",
                    (row["id"],),
                )
                deleted += 1
        else:
            cur.execute(
                "UPDATE normalized_route_segment_rule_reviews SET route_version_id = ? WHERE id = ?",
                (keep_id, row["id"]),
            )
            moved += 1
    return {"moved": moved, "deleted_dup": deleted}


def remount_factor_reviews(cur: sqlite3.Cursor, old_id: int, keep_id: int) -> dict[str, int]:
    moved = deleted = 0
    rows = list(
        cur.execute(
            """
            SELECT id, segment_id, factor_name, updated_at
            FROM normalized_route_segment_factor_reviews
            WHERE route_version_id = ?
            ORDER BY updated_at DESC, id DESC
            """,
            (old_id,),
        )
    )
    for row in rows:
        existing = cur.execute(
            """
            SELECT id, updated_at
            FROM normalized_route_segment_factor_reviews
            WHERE route_version_id = ? AND segment_id = ? AND factor_name = ?
            """,
            (keep_id, row["segment_id"], row["factor_name"]),
        ).fetchone()
        if existing:
            keep_ts = str(existing["updated_at"] or "")
            old_ts = str(row["updated_at"] or "")
            if old_ts > keep_ts:
                cur.execute(
                    "DELETE FROM normalized_route_segment_factor_reviews WHERE id = ?",
                    (existing["id"],),
                )
                cur.execute(
                    "UPDATE normalized_route_segment_factor_reviews SET route_version_id = ? WHERE id = ?",
                    (keep_id, row["id"]),
                )
                moved += 1
            else:
                cur.execute(
                    "DELETE FROM normalized_route_segment_factor_reviews WHERE id = ?",
                    (row["id"],),
                )
                deleted += 1
        else:
            cur.execute(
                "UPDATE normalized_route_segment_factor_reviews SET route_version_id = ? WHERE id = ?",
                (keep_id, row["id"]),
            )
            moved += 1
    return {"moved": moved, "deleted_dup": deleted}


def remount_rule_packages(cur: sqlite3.Cursor, old_id: int, keep_id: int) -> int:
    cur.execute(
        "UPDATE finalized_rule_packages SET route_version_id = ? WHERE route_version_id = ?",
        (keep_id, old_id),
    )
    return cur.rowcount or 0


def cleanup(db_path: Path, dry_run: bool = False) -> int:
    if not db_path.exists():
        print("ERROR: database not found: {}".format(db_path), file=sys.stderr)
        return 2

    backup_path = None
    if not dry_run:
        backup_path = db_path.with_name("{}.bak-{}".format(db_path.name, utc_stamp()))
        shutil.copy2(db_path, backup_path)
        print("Backup written: {}".format(backup_path))

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    cur = con.cursor()

    versions = fetch_versions(cur)
    if not versions:
        print("No normalized_route_versions rows found.")
        con.close()
        return 0

    by_project = defaultdict(list)
    for row in versions:
        by_project[int(row["project_id"])].append(row)

    total_deleted = 0
    total_remapped_packages = 0
    plan_lines = []

    for project_id, rows in sorted(by_project.items()):
        groups = defaultdict(list)
        for row in rows:
            groups[canonical_route_hash(row["route_json"])].append(row)

        for content_hash, group in groups.items():
            if len(group) < 2:
                continue
            keep = sorted(group, key=lambda r: (int(r["version"] or 0), int(r["id"])))[-1]
            discard = [r for r in group if int(r["id"]) != int(keep["id"])]
            drop_labels = ["id{}/V{}".format(r["id"], r["version"]) for r in discard]
            plan_lines.append(
                "project={} hash={} keep=id{}/V{} drop={}".format(
                    project_id,
                    content_hash[:12],
                    keep["id"],
                    keep["version"],
                    drop_labels,
                )
            )
            if dry_run:
                total_deleted += len(discard)
                continue

            for old in discard:
                old_id = int(old["id"])
                keep_id = int(keep["id"])
                rr = remount_rule_reviews(cur, old_id, keep_id)
                fr = remount_factor_reviews(cur, old_id, keep_id)
                pkg_n = remount_rule_packages(cur, old_id, keep_id)
                total_remapped_packages += pkg_n
                cur.execute("DELETE FROM normalized_route_versions WHERE id = ?", (old_id,))
                total_deleted += 1
                plan_lines.append(
                    "  remounted old={} -> keep={} rule_reviews={} factor_reviews={} packages={}".format(
                        old_id, keep_id, rr, fr, pkg_n
                    )
                )

    renumbered = 0
    if not dry_run:
        remaining = fetch_versions(cur)
        by_project_left = defaultdict(list)
        for row in remaining:
            by_project_left[int(row["project_id"])].append(row)
        for project_id, rows in sorted(by_project_left.items()):
            ordered = sorted(
                rows,
                key=lambda r: (
                    str(r["created_at"] or ""),
                    int(r["version"] or 0),
                    int(r["id"]),
                ),
            )
            for idx, row in enumerate(ordered, start=1):
                if int(row["version"] or 0) != idx:
                    cur.execute(
                        "UPDATE normalized_route_versions SET version = ? WHERE id = ?",
                        (idx, int(row["id"])),
                    )
                    renumbered += 1
                    plan_lines.append(
                        "renumber project={} id={}: V{} -> V{}".format(
                            project_id, row["id"], row["version"], idx
                        )
                    )

    for line in plan_lines:
        print(line)

    if dry_run:
        print("\nDRY RUN: would delete {} duplicate version row(s). No changes written.".format(total_deleted))
        con.close()
        return 0

    con.commit()

    left = fetch_versions(cur)
    print("\n=== remaining versions ===")
    for row in left:
        h = canonical_route_hash(row["route_json"])[:12]
        print(
            "id={} project={} V{} segs={} hash={} created={}".format(
                row["id"],
                row["project_id"],
                row["version"],
                row["segment_count"],
                h,
                row["created_at"],
            )
        )

    dangling_reviews = cur.execute(
        """
        SELECT COUNT(*) AS c
        FROM normalized_route_segment_rule_reviews r
        LEFT JOIN normalized_route_versions v ON v.id = r.route_version_id
        WHERE v.id IS NULL
        """
    ).fetchone()["c"]
    dangling_packages = cur.execute(
        """
        SELECT COUNT(*) AS c
        FROM finalized_rule_packages p
        LEFT JOIN normalized_route_versions v ON v.id = p.route_version_id
        WHERE p.route_version_id IS NOT NULL AND v.id IS NULL
        """
    ).fetchone()["c"]

    print(
        "\nDone. deleted={} packages_remapped={} renumbered={} dangling_reviews={} dangling_packages={}".format(
            total_deleted,
            total_remapped_packages,
            renumbered,
            dangling_reviews,
            dangling_packages,
        )
    )
    if backup_path:
        print("Backup: {}".format(backup_path))

    con.close()
    if dangling_reviews or dangling_packages:
        print("WARNING: dangling FK references remain.", file=sys.stderr)
        return 1
    return 0


def default_db_path() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "db" / "process_mind.db"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path(), help="Path to process_mind.db")
    parser.add_argument("--dry-run", action="store_true", help="Print plan only; do not modify DB")
    args = parser.parse_args(argv)
    return cleanup(args.db.resolve(), dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
