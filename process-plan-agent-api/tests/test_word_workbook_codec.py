"""The workbook manifest stores source paths relative to the API project root."""
import hashlib
import json
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
CODEC_DIR = API_ROOT.parent / "outputs/word-knowledge-expansion"
sys.path.insert(0, str(CODEC_DIR))
import workbook_codec


def test_source_manifest_paths_resolve_from_api_project_root():
    source = json.loads((API_ROOT / "knowledge/demo/word_sources.json").read_text())[0]

    path = workbook_codec.resolve_source_path(source["source_path"])

    assert path == API_ROOT / source["source_path"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == source["sha256"]


def test_route_steps_do_not_repeat_long_parent_text_and_still_roundtrip():
    tables = workbook_codec.export_tables()
    rows = tables["典型路线"]
    headers = rows[0]
    route_id = "WD01-44-stage_overview"
    route_rows = [row for row in rows[1:] if row[headers.index("记录ID")] == route_id]
    long_columns = ("适用范围", "前提条件", "结论或要求", "例外", "原文", "来源定位")

    assert len(route_rows) > 1
    for column in long_columns:
        column_index = headers.index(column)
        assert all(row[column_index] in (None, "") for row in route_rows[1:])

    compiled, _, _ = workbook_codec.compile_tables(tables)
    actual = next(record for record in compiled if record["id"] == route_id)
    expected = next(
        record for record in json.loads((API_ROOT / "knowledge/demo/word_records.json").read_text())
        if record["id"] == route_id
    )
    assert actual["guidance"] == expected["guidance"]
    assert actual["source"] == expected["source"]
