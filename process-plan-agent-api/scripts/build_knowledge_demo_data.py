"""Build versioned local JSON records for the machining knowledge demo."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import openpyxl


SHEETS = {
    "设备": "equipment",
    "刀具": "tool",
    "量具": "gauge",
    "加工能力": "capability",
}


def _records_from_sheet(path: Path, sheet_name: str, category: str) -> list[dict[str, Any]]:
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    worksheet = workbook[sheet_name]
    rows = worksheet.iter_rows(values_only=True)
    headers = [str(value or "").strip() for value in next(rows)]
    result = []
    for row_number, values in enumerate(rows, start=2):
        record = {headers[index]: value for index, value in enumerate(values) if index < len(headers) and value is not None}
        if not record:
            continue
        record_id = str(record.get(f"{category.upper()}ID") or record.get("能力ID") or f"{category}-{row_number}")
        result.append({
            "id": record_id,
            "category": category,
            "title": str(record.get("设备名称") or record.get("刀具名称") or record.get("量具名称") or record.get("加工特征") or sheet_name),
            "fields": record,
            "source": {
                "document_name": str(record.get("来源文件") or path.name),
                "worksheet": str(record.get("来源工作表") or sheet_name),
                "row_no": record.get("来源行号", row_number),
                "cell_range": str(record.get("来源单元格范围") or ""),
                "identity": f"{sheet_name}:{record.get('来源工作表', sheet_name)}:{record.get('来源单元格范围', row_number)}",
            },
        })
    workbook.close()
    return result


def _history_records(process_dir: Path) -> list[dict[str, Any]]:
    result = []
    for path in sorted(process_dir.glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        procedure = document.get("工艺规程信息", {})
        part = procedure.get("零件信息", {})
        for operation in procedure.get("工序", []):
            steps = operation.get("工步", []) or []
            devices = operation.get("设备", []) or []
            tools = operation.get("刀具", []) or []
            gauges = list(dict.fromkeys(
                str(gauge)
                for step in steps
                for gauge in (step.get("量具", []) or [])
            ))
            fields = {
                "零件编号": part.get("编号", ""),
                "零件名称": part.get("名称", ""),
                "图号": part.get("图号", ""),
                "材料": part.get("材料", ""),
                "毛坯": part.get("毛坯", ""),
                "工序号": operation.get("工序号", ""),
                "工序名称": operation.get("工序名称", ""),
                "工序内容": operation.get("工序内容", ""),
                "技术要求": operation.get("技术要求", ""),
                "备注": operation.get("备注", ""),
                "设备": devices,
                "刀具": tools,
                "量具": gauges,
                "工步": steps,
                "工艺规程编号": procedure.get("编号", ""),
                "版本": procedure.get("版本", ""),
            }
            identity = f"{part.get('编号', path.stem)}:工序{operation.get('工序号', '')}"
            result.append({
                "id": identity,
                "category": "history",
                "title": f"{part.get('名称', '未命名零件')} · 工序{operation.get('工序号', '')} {operation.get('工序名称', '')}".strip(),
                "fields": fields,
                "source": {
                    "document_name": path.name,
                    "identity": identity,
                    "worksheet": "工艺规程信息/工序",
                    "row_no": None,
                    "cell_range": None,
                },
            })
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--process-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("knowledge/demo/records.json"))
    args = parser.parse_args()

    records = []
    for sheet_name, category in SHEETS.items():
        records.extend(_records_from_sheet(args.workbook, sheet_name, category))
    records.extend(_history_records(args.process_dir))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(records, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {len(records)} local knowledge records to {args.output}")


if __name__ == "__main__":
    main()
