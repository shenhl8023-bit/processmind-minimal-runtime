# Rule Package Review, Publish, and Download Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fourth-step compound action with independent “规则审核”, “发布规则包”, and “下载当前版本” actions, with repeatable read-only downloads of the persisted published package.

**Architecture:** Move ZIP creation to a backend archive service and expose a read-only download endpoint for a specific published package ID. Refactor the frontend export composable into publish-only and download-only composables, then make `FinalizeView` orchestrate rule review, publish, and download as three explicit state machines.

**Tech Stack:** FastAPI, SQLAlchemy async, Python `zipfile`, Vue 3 Composition API, TypeScript 5.9, Axios, Vitest, pytest.

## Global Constraints

- The three user-facing action labels are exactly `规则审核`, `发布规则包`, and `下载当前版本`.
- Publishing creates a version but never starts a browser download.
- Downloading never parses, confirms, compiles, saves, publishes, supersedes, or archives a rule package.
- Only a package whose current status is `published` may be downloaded from the new endpoint.
- A current package is usable only when route version, content hash, and confirmed-rule state still match the fourth-step workspace.
- Keep the existing rule package V2 contract, KmAI fixed adapter, workflow revision guard, and fifth-step behavior unchanged.
- Keep `重新识别全部` separate from `规则审核`.
- Do not add historical-version UI in this slice.
- Do not create Git commits unless the boss explicitly requests them; preserve task boundaries in the working diff instead.
- Design source of truth: `docs/superpowers/specs/2026-07-31-rule-package-action-split-design.md`.

---

## File Structure

### Backend

- Create `process-plan-agent-api/app/services/rule_packages/archive.py`: build an immutable ZIP from one persisted V2 package row.
- Create `process-plan-agent-api/tests/test_rule_package_archive.py`: unit-test archive contents and authoritative snapshot behavior.
- Modify `process-plan-agent-api/app/routers/extract.py`: add the read-only `/{package_id}/download` route.
- Modify `process-plan-agent-api/app/main.py`: expose `Content-Disposition` to the cross-origin development UI.
- Modify `process-plan-agent-api/tests/test_rule_package_api.py`: cover download status rules and zero-write repeated downloads.

### Frontend

- Modify `process-plan-agent-ui/src/api/extract.ts`: request ZIP blobs and parse the response filename.
- Create `process-plan-agent-ui/src/composables/useFinalizedRulePackageDownload.ts` and its spec: download-only state and error handling.
- Rename `process-plan-agent-ui/src/composables/useFinalizeRulePackageExport.ts` and its spec to `useFinalizeRulePackagePublish.*`: retain build, compile, review, and save; remove ZIP creation and download.
- Rename `process-plan-agent-ui/src/composables/useRulePackageExportReview.ts` and its spec to `useRulePackagePublishReview.*`.
- Rename `process-plan-agent-ui/src/components/finalize/RulePackageExportReviewDialog.vue` and its spec to `RulePackagePublishReviewDialog.*`.
- Create `process-plan-agent-ui/src/utils/finalizeRulePackageActionState.ts` and its spec: pure labels and disabled-state decisions.
- Modify `process-plan-agent-ui/src/views/FinalizeView.vue`: render and orchestrate the three buttons and current package metadata.

---

### Task 1: Build ZIP Archives From Persisted V2 Packages

**Files:**
- Create: `process-plan-agent-api/app/services/rule_packages/archive.py`
- Create: `process-plan-agent-api/tests/test_rule_package_archive.py`

**Interfaces:**
- Consumes: `FinalizedRulePackage`, `v2_package_from_row()`, `load_legacy_mapping_snapshot_for_package()`, and `build_kmai_compatibility_export()`.
- Produces: `RulePackageArchive(filename: str, content: bytes)` and `build_finalized_rule_package_archive(row: FinalizedRulePackage) -> RulePackageArchive`.
- Raises: `RulePackageArchiveError` when the persisted package is not V2 or cannot produce valid KmAI files.

- [ ] **Step 1: Write the failing archive-content test**

```python
from io import BytesIO
import json
from zipfile import ZipFile

from app.models.models import FinalizedRulePackage
from app.services.rule_packages.archive import build_finalized_rule_package_archive


def _persisted_row(payload):
    return FinalizedRulePackage(
        id=7,
        project_id=payload["manifest"]["project_id"],
        route_version_id=payload["manifest"]["route_version_id"],
        version=3,
        package_name=payload["manifest"]["package_name"],
        schema_version="2.0",
        status="published",
        manifest_json=json.dumps(payload["manifest"], ensure_ascii=False),
        input_schema_json=json.dumps(payload["input_schema"], ensure_ascii=False),
        route_catalog_json=json.dumps(payload["route_catalog"], ensure_ascii=False),
        route_rules_json=json.dumps(payload["route_rules"], ensure_ascii=False),
        test_cases_json=json.dumps(payload["test_cases"], ensure_ascii=False),
        rule_report_md="# 权威规则报告",
        validation_report_json=json.dumps({"valid": True}, ensure_ascii=False),
        content_hash="a" * 64,
    )


def test_archive_contains_persisted_v2_and_kmai_files(rule_package_v2_payload):
    archive = build_finalized_rule_package_archive(_persisted_row(rule_package_v2_payload))

    assert archive.filename.endswith("_v3.zip")
    with ZipFile(BytesIO(archive.content)) as package_zip:
        assert set(package_zip.namelist()) == {
            "manifest.json",
            "input_schema.json",
            "route_catalog.json",
            "route_rules.json",
            "test_cases.json",
            "rule_report.md",
            "validation_report.json",
            "kmai-v1/factor_schema.json",
            "kmai-v1/factor_expansion_rules.json",
            "kmai-v1/route_catalog.json",
            "kmai-v1/route_rules.json",
            "kmai-v1/README-替换说明.txt",
        }
        assert json.loads(package_zip.read("route_rules.json")) == rule_package_v2_payload["route_rules"]
        assert package_zip.read("rule_report.md").decode("utf-8") == "# 权威规则报告"
```

- [ ] **Step 2: Run the focused test and verify the missing module failure**

Run from `process-plan-agent-api`:

```powershell
..\.runtime\python\python.exe -m pytest tests/test_rule_package_archive.py -v
```

Expected: collection fails because `app.services.rule_packages.archive` does not exist.

- [ ] **Step 3: Implement archive primitives and deterministic writers**

```python
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import json
import re
from zipfile import ZIP_DEFLATED, ZipFile

from app.models.models import FinalizedRulePackage
from app.services.finalized_rule_package_helpers import json_loads
from app.services.rule_packages.kmai_export import build_kmai_compatibility_export
from app.services.rule_packages.lifecycle import (
    RulePackageLifecycleError,
    load_legacy_mapping_snapshot_for_package,
    v2_package_from_row,
)


class RulePackageArchiveError(ValueError):
    pass


@dataclass(frozen=True)
class RulePackageArchive:
    filename: str
    content: bytes


def _json_text(value: object) -> str:
    return f"{json.dumps(value, ensure_ascii=False, indent=2)}\n"


def _safe_filename_part(value: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", value).strip() or "process_route_rules"


def _write_text(package_zip: ZipFile, name: str, value: str) -> None:
    package_zip.writestr(name, value.encode("utf-8"))
```

- [ ] **Step 4: Implement manual-factor guidance and README text**

```python
def _manual_boolean_factors(files: dict[str, dict]) -> list[tuple[str, str]]:
    factors = files.get("factor_schema.json", {}).get("factors", [])
    return [
        (str(item["factor_key"]), str(item.get("name") or item["factor_key"]))
        for item in factors
        if isinstance(item, dict)
        and item.get("source_mode") == "manual_override"
        and item.get("value_type") == "boolean"
        and item.get("factor_key")
    ]


def _replacement_readme(target_directory: str, files: dict[str, dict]) -> str:
    manual_lines = [f"- {key}: {name}" for key, name in _manual_boolean_factors(files)] or ["- None"]
    return "\n".join([
        "KmAI 规则文件替换说明",
        "",
        f"目标目录：{target_directory}",
        "",
        "1. 先停止 KmAI Agent。",
        "2. 备份目标目录中同名的四个 JSON 文件。",
        "3. 将本目录中的 factor_schema.json、factor_expansion_rules.json、route_catalog.json、route_rules.json 复制到目标目录并覆盖。",
        "4. 不要删除或覆盖原有 group_match_rules.json。",
        "5. 重新启动 KmAI Agent；后续工艺路线生成将使用本次导出的 ProcessMind 规则。",
        "6. route_catalog.json 的 template_group_aliases 为 ProcessMind 附加元数据；KmAI v1 会忽略它，不影响路线生成。",
        "",
        "Manual boolean factors require manual.factor_overrides values (true/false):",
        *manual_lines,
        "",
    ])
```

- [ ] **Step 5: Implement the archive builder**

```python
def build_finalized_rule_package_archive(row: FinalizedRulePackage) -> RulePackageArchive:
    try:
        package = v2_package_from_row(row)
    except RulePackageLifecycleError as error:
        raise RulePackageArchiveError(str(error)) from error

    compatibility = build_kmai_compatibility_export(
        package,
        legacy_mapping_snapshot=load_legacy_mapping_snapshot_for_package(row),
    )
    if not compatibility.valid:
        messages = "；".join(issue.message for issue in compatibility.errors)
        raise RulePackageArchiveError(messages or "已发布规则包无法生成 KmAI 兼容文件")

    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as package_zip:
        persisted_files = {
            "manifest.json": package.manifest.model_dump(mode="json"),
            "input_schema.json": package.input_schema.model_dump(mode="json"),
            "route_catalog.json": package.route_catalog.model_dump(mode="json"),
            "route_rules.json": package.route_rules.model_dump(mode="json"),
            "test_cases.json": [item.model_dump(mode="json") for item in package.test_cases],
            "validation_report.json": json_loads(row.validation_report_json),
        }
        for name, value in persisted_files.items():
            _write_text(package_zip, name, _json_text(value))
        _write_text(package_zip, "rule_report.md", row.rule_report_md or "")
        for name, value in compatibility.files.items():
            _write_text(package_zip, f"kmai-v1/{name}", _json_text(value))
        _write_text(
            package_zip,
            "kmai-v1/README-替换说明.txt",
            _replacement_readme(compatibility.target_directory, compatibility.files),
        )

    filename = f"{_safe_filename_part(row.package_name)}_v{row.version}.zip"
    return RulePackageArchive(filename=filename, content=output.getvalue())
```

- [ ] **Step 6: Run the archive tests**

```powershell
..\.runtime\python\python.exe -m pytest tests/test_rule_package_archive.py -v
```

Expected: all archive service tests pass.

---

### Task 2: Add a Read-Only Published-Package Download Endpoint

**Files:**
- Modify: `process-plan-agent-api/app/routers/extract.py:8-66,574-583`
- Modify: `process-plan-agent-api/app/main.py:41-47`
- Modify: `process-plan-agent-api/tests/test_rule_package_api.py`

**Interfaces:**
- Consumes: `build_finalized_rule_package_archive()` from Task 1.
- Produces: `GET /api/extract/finalized-rule-packages/{package_id}/download` returning `application/zip`.
- Error contract: `404` for a missing package, `409` for a non-`published` package, and `422` when a persisted V2 archive cannot be produced.

- [ ] **Step 1: Write the failing repeated-download API test**

```python
from io import BytesIO
from zipfile import ZipFile


def test_published_package_download_is_repeatable_and_read_only(rule_package_v2_payload):
    saved = client.post(
        "/api/extract/finalized-rule-packages",
        json=_v2_save_payload(rule_package_v2_payload),
    )
    assert saved.status_code == 200
    package_id = saved.json()["id"]
    before = client.get(
        "/api/extract/finalized-rule-packages",
        params={"project_id": 12},
    ).json()

    first = client.get(
        f"/api/extract/finalized-rule-packages/{package_id}/download",
        headers={"Origin": "http://localhost:5173"},
    )
    second = client.get(f"/api/extract/finalized-rule-packages/{package_id}/download")

    assert first.status_code == second.status_code == 200
    assert first.headers["content-type"] == "application/zip"
    assert "filename*=UTF-8''" in first.headers["content-disposition"]
    assert "content-disposition" in first.headers["access-control-expose-headers"].lower()
    with ZipFile(BytesIO(first.content)) as package_zip:
        assert "manifest.json" in package_zip.namelist()
        assert "kmai-v1/route_rules.json" in package_zip.namelist()

    after = client.get(
        "/api/extract/finalized-rule-packages",
        params={"project_id": 12},
    ).json()
    assert [(item["id"], item["version"], item["status"]) for item in after] == [
        (item["id"], item["version"], item["status"]) for item in before
    ]
```

- [ ] **Step 2: Write failing missing and superseded state tests**

```python
def test_download_rejects_missing_and_superseded_packages(rule_package_v2_payload):
    assert client.get("/api/extract/finalized-rule-packages/999999/download").status_code == 404

    first = client.post(
        "/api/extract/finalized-rule-packages",
        json=_v2_save_payload(rule_package_v2_payload),
    ).json()
    second = client.post(
        "/api/extract/finalized-rule-packages",
        json=_v2_save_payload(rule_package_v2_payload),
    )
    assert second.status_code == 200

    rejected = client.get(f"/api/extract/finalized-rule-packages/{first['id']}/download")
    assert rejected.status_code == 409
    assert "当前发布版本" in rejected.json()["detail"]


def test_download_rejects_archived_package(rule_package_v2_payload, isolated_rule_package_db):
    saved = client.post(
        "/api/extract/finalized-rule-packages",
        json=_v2_save_payload(rule_package_v2_payload),
    ).json()

    async def archive_package():
        async with isolated_rule_package_db() as session:
            row = await session.get(FinalizedRulePackage, saved["id"])
            row.status = "archived"
            await session.commit()

    asyncio.run(archive_package())
    rejected = client.get(f"/api/extract/finalized-rule-packages/{saved['id']}/download")
    assert rejected.status_code == 409
```

Change the existing autouse fixture from `yield` to `yield session_factory`, and import `FinalizedRulePackage` beside `NormalizedRouteVersion` and `Project`, so the archived-state test can update its isolated database directly.

- [ ] **Step 3: Run both API tests and verify they fail before the route exists**

Run from `process-plan-agent-api`:

```powershell
..\.runtime\python\python.exe -m pytest tests/test_rule_package_api.py -k "download" -v
```

Expected: the endpoint tests fail because the route is not registered.

- [ ] **Step 4: Implement the endpoint without database writes**

Add `quote`, `Response`, and the archive service imports, then add:

```python
@router.get("/finalized-rule-packages/{package_id}/download")
async def download_finalized_rule_package(
    package_id: int,
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(FinalizedRulePackage, package_id)
    if row is None:
        raise HTTPException(404, "规则包不存在。")
    if row.status != "published":
        raise HTTPException(409, "只能下载当前发布版本的规则包。")
    try:
        archive = build_finalized_rule_package_archive(row)
    except RulePackageArchiveError as error:
        raise HTTPException(422, str(error)) from error
    return Response(
        content=archive.content,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(archive.filename)}",
        },
    )
```

The imports are:

```python
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, Response
from app.services.rule_packages.archive import (
    RulePackageArchiveError,
    build_finalized_rule_package_archive,
)
```

Expose the filename response header to the development UI origin in `app/main.py`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)
```

- [ ] **Step 5: Run focused backend tests**

```powershell
..\.runtime\python\python.exe -m pytest tests/test_rule_package_archive.py tests/test_rule_package_api.py -v
```

Expected: archive and API tests pass, including the repeated-download state comparison.

---

### Task 3: Add the Frontend Download API and Download-Only Composable

**Files:**
- Modify: `process-plan-agent-ui/src/api/extract.ts:504-557`
- Create: `process-plan-agent-ui/src/composables/useFinalizedRulePackageDownload.ts`
- Create: `process-plan-agent-ui/src/composables/useFinalizedRulePackageDownload.spec.ts`

**Interfaces:**
- Produces API function: `downloadFinalizedRulePackageArchive(packageId: number) -> Promise<{ blob: Blob; filename: string | null }>`.
- Produces composable: `useFinalizedRulePackageDownload(options)` returning `{ downloadingRulePackage, downloadCurrentRulePackage }`.
- The composable accepts `packageId`, `packageVersion`, `projectName`, and `onDownloadIssue`; it has no rule-card, compile, review, or save dependency.

- [ ] **Step 1: Write failing composable tests**

```typescript
import { ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  downloadArchive: vi.fn(),
  downloadBlob: vi.fn(),
}))

vi.mock('@/api', () => ({
  downloadFinalizedRulePackageArchive: mocks.downloadArchive,
}))
vi.mock('@/utils/exportArchive', () => ({ downloadBlob: mocks.downloadBlob }))

import { rulePackageArchiveFilename } from '@/api/extract'
import { useFinalizedRulePackageDownload } from './useFinalizedRulePackageDownload'

describe('useFinalizedRulePackageDownload', () => {
  beforeEach(() => {
    mocks.downloadArchive.mockReset()
    mocks.downloadBlob.mockReset()
  })

  it('parses encoded and quoted server filenames', () => {
    expect(rulePackageArchiveFilename(
      "attachment; filename*=UTF-8''%E8%A7%84%E5%88%99%E5%8C%85_v3.zip",
    )).toBe('规则包_v3.zip')
    expect(rulePackageArchiveFilename('attachment; filename="rules_v3.zip"')).toBe('rules_v3.zip')
  })

  it('repeatedly downloads the same published package', async () => {
    const blob = new Blob(['zip'], { type: 'application/zip' })
    mocks.downloadArchive.mockResolvedValue({ blob, filename: '规则包_v3.zip' })
    const issue = vi.fn()
    const download = useFinalizedRulePackageDownload({
      packageId: ref(17),
      packageVersion: ref(3),
      projectName: ref('轴类项目'),
      onDownloadIssue: issue,
    })

    await download.downloadCurrentRulePackage()
    await download.downloadCurrentRulePackage()

    expect(mocks.downloadArchive).toHaveBeenNthCalledWith(1, 17)
    expect(mocks.downloadArchive).toHaveBeenNthCalledWith(2, 17)
    expect(mocks.downloadBlob).toHaveBeenCalledTimes(2)
    expect(mocks.downloadBlob).toHaveBeenCalledWith(blob, '规则包_v3.zip')
    expect(issue).not.toHaveBeenCalled()
  })

  it('reports failure without clearing package metadata', async () => {
    mocks.downloadArchive.mockRejectedValue(new Error('network down'))
    const packageId = ref(17)
    const issue = vi.fn()
    const download = useFinalizedRulePackageDownload({
      packageId,
      packageVersion: ref(3),
      projectName: ref('轴类项目'),
      onDownloadIssue: issue,
    })

    await download.downloadCurrentRulePackage()

    expect(packageId.value).toBe(17)
    expect(mocks.downloadBlob).not.toHaveBeenCalled()
    expect(issue).toHaveBeenCalledWith(expect.objectContaining({ title: '规则包下载失败' }))
  })

  it('reads backend detail from a failed blob response', async () => {
    mocks.downloadArchive.mockRejectedValue({
      response: {
        data: new Blob([JSON.stringify({ detail: '只能下载当前发布版本的规则包。' })], {
          type: 'application/json',
        }),
      },
    })
    const issue = vi.fn()
    const download = useFinalizedRulePackageDownload({
      packageId: ref(17),
      packageVersion: ref(3),
      projectName: ref('轴类项目'),
      onDownloadIssue: issue,
    })

    await download.downloadCurrentRulePackage()

    expect(issue).toHaveBeenCalledWith(expect.objectContaining({
      details: '只能下载当前发布版本的规则包。',
    }))
  })
})
```

- [ ] **Step 2: Run the new Vitest file and verify missing exports**

Run from `process-plan-agent-ui`:

```powershell
npm.cmd test -- src/composables/useFinalizedRulePackageDownload.spec.ts
```

Expected: test collection fails because the API helper and composable do not exist.

- [ ] **Step 3: Add content-disposition parsing and the blob API call**

```typescript
export function rulePackageArchiveFilename(contentDisposition?: string): string | null {
  if (!contentDisposition) return null
  const encoded = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  if (encoded) return decodeURIComponent(encoded)
  return contentDisposition.match(/filename="([^"]+)"/i)?.[1] || null
}

export async function downloadFinalizedRulePackageArchive(packageId: number) {
  const response = await api.get(
    `/api/extract/finalized-rule-packages/${packageId}/download`,
    { responseType: 'blob' },
  )
  return {
    blob: response.data as Blob,
    filename: rulePackageArchiveFilename(response.headers['content-disposition']),
  }
}
```

- [ ] **Step 4: Implement the download-only composable**

```typescript
import { ref, type Ref } from 'vue'
import { downloadFinalizedRulePackageArchive } from '@/api'
import { downloadBlob } from '@/utils/exportArchive'

type DownloadIssue = { title: string; summary: string; details?: string }
type UseFinalizedRulePackageDownloadOptions = {
  packageId: Readonly<Ref<number | null>>
  packageVersion: Readonly<Ref<number | null>>
  projectName: Readonly<Ref<string>>
  onDownloadIssue?: (issue: DownloadIssue) => void
}

function safeFilenamePart(value: string) {
  return value.replace(/[\\/:*?"<>|]/g, '_')
}

async function downloadErrorDetail(error: any): Promise<string> {
  const data = error?.response?.data
  if (data instanceof Blob) {
    try {
      const parsed = JSON.parse(await data.text())
      return String(parsed?.detail || '未知错误')
    } catch {
      return error?.message || '未知错误'
    }
  }
  return String(data?.detail || error?.message || '未知错误')
}

export function useFinalizedRulePackageDownload(options: UseFinalizedRulePackageDownloadOptions) {
  const downloadingRulePackage = ref(false)

  async function downloadCurrentRulePackage() {
    const packageId = options.packageId.value
    if (!packageId || downloadingRulePackage.value) return
    downloadingRulePackage.value = true
    try {
      const archive = await downloadFinalizedRulePackageArchive(packageId)
      const fallback = `${safeFilenamePart(options.projectName.value || '规则包')}_规则包_v${options.packageVersion.value || 1}.zip`
      downloadBlob(archive.blob, archive.filename || fallback)
    } catch (error: any) {
      const detail = await downloadErrorDetail(error)
      options.onDownloadIssue?.({
        title: '规则包下载失败',
        summary: '当前已发布版本未能下载，请稍后重试。',
        details: detail,
      })
    } finally {
      downloadingRulePackage.value = false
    }
  }

  return { downloadingRulePackage, downloadCurrentRulePackage }
}
```

- [ ] **Step 5: Run the download tests**

```powershell
npm.cmd test -- src/composables/useFinalizedRulePackageDownload.spec.ts
```

Expected: parser, success, repeated download, and failure tests pass.

---

### Task 4: Refactor Export Into Publish-Only Review and Persistence

**Files:**
- Rename: `process-plan-agent-ui/src/composables/useFinalizeRulePackageExport.ts` to `useFinalizeRulePackagePublish.ts`
- Rename: `process-plan-agent-ui/src/composables/useFinalizeRulePackageExport.spec.ts` to `useFinalizeRulePackagePublish.spec.ts`
- Rename: `process-plan-agent-ui/src/composables/useRulePackageExportReview.ts` to `useRulePackagePublishReview.ts`
- Rename: `process-plan-agent-ui/src/composables/useRulePackageExportReview.spec.ts` to `useRulePackagePublishReview.spec.ts`
- Rename: `process-plan-agent-ui/src/components/finalize/RulePackageExportReviewDialog.vue` to `RulePackagePublishReviewDialog.vue`
- Rename: `process-plan-agent-ui/src/components/finalize/RulePackageExportReviewDialog.spec.ts` to `RulePackagePublishReviewDialog.spec.ts`

**Interfaces:**
- Produces: `useFinalizeRulePackagePublish(options)` returning `{ publishingRulePackage, publishRulePackage }`.
- Produces: `RulePackagePublishReview`, `buildPublishReview()`, and `useRulePackagePublishReview()`.
- Publish callback: `onPublished(packageValue: SaveFinalizedRulePackageResponse): void` receives the full saved package metadata.
- Removes: `createZipBlob`, `downloadBlob`, frontend KmAI README creation, and all browser-download calls from the publish composable.

- [ ] **Step 1: Rewrite the success test as publish-only behavior**

Rename existing test symbols, remove ZIP/download mocks, and use:

```typescript
it('compiles once, waits for review, and publishes without a download dependency', async () => {
  const review = vi.fn().mockResolvedValue(true)
  const onPublished = vi.fn()
  mocks.compileRulePackage.mockResolvedValueOnce(compiled(firstPackage, true))
  const saved = savedPackage(firstPackage)
  mocks.saveFinalizedRulePackage.mockResolvedValueOnce(saved)

  const { publishRulePackage } = createPublish({
    onPublishReviewRequired: review,
    onPublished,
  })
  await publishRulePackage()

  expect(mocks.compileRulePackage).toHaveBeenCalledTimes(1)
  expect(mocks.saveFinalizedRulePackage).toHaveBeenCalledTimes(1)
  expect(onPublished).toHaveBeenCalledWith(saved)
})
```

Keep the existing cancellation, blocked validation, unavailable registry, failed binding, source-segment mapping, and workflow-conflict tests. Update them to call `publishRulePackage()`.

- [ ] **Step 2: Update review and dialog tests for publish language**

```typescript
expect(html).toContain('审核并发布规则包')
expect(html).toContain('确认后将发布规则包')
expect(html).toMatch(/<button[^>]*>\s*确认发布\s*<\/button>/)
expect(html).not.toContain('确认导出')
```

Keep ready/blocked, manual-factor guidance, locate, cancellation, and stale-promise assertions.

- [ ] **Step 3: Run renamed tests and verify symbol/copy failures**

```powershell
npm.cmd test -- src/composables/useFinalizeRulePackagePublish.spec.ts src/composables/useRulePackagePublishReview.spec.ts src/components/finalize/RulePackagePublishReviewDialog.spec.ts
```

Expected: tests fail until renamed files and exports exist.

- [ ] **Step 4: Rename publish-review types and helpers consistently**

```typescript
export type RulePackagePublishReviewStatus = 'ready' | 'blocked'
export type PublishBlockDetail = {
  code: string
  message: string
  processName: string
  sourceText: string
  sourceSegmentId: string
}
export type RulePackagePublishReview = {
  status: RulePackagePublishReviewStatus
  projectName: string
  processCount: number
  ruleCount: number
  validation: CompileRulePackageResponse['validation'] | null
  kmaiCompatibility: CompileRulePackageResponse['kmai_compatibility'] | null
  manualFactors: ManualFactorSummary[]
  rulePackage: RulePackageV2 | null
  details: PublishBlockDetail[]
}
```

Rename `buildExportReview` to `buildPublishReview`, `buildExportBlockDetails` to `buildPublishBlockDetails`, `ExportReviewIssue` to `PublishReviewIssue`, and `useRulePackageExportReview` to `useRulePackagePublishReview`.

- [ ] **Step 5: Remove ZIP assembly from the publish composable**

Keep current pre-compile guards, compile request construction, rule-report creation, save payload, revision-conflict reload, and structured issue reporting. After a successful save, the function must end with:

```typescript
const savedPackage = await saveFinalizedRulePackage({
  project_id: options.projectId.value,
  expected_workflow_revision: options.savedRoute.value?.workflow_revision || 0,
  route_version_id: options.savedRoute.value?.route_id || null,
  package_name: packageName,
  schema_version: '2.0',
  manifest: compiled.package.manifest,
  input_schema: compiled.package.input_schema,
  route_catalog: compiled.package.route_catalog,
  route_rules: compiled.package.route_rules,
  test_cases: compiled.package.test_cases || [],
  rule_report_md: ruleReport,
  validation_report: compiled.validation,
})
options.onPublished?.(savedPackage)
```

Rename `UseFinalizeRulePackageExportOptions` to `UseFinalizeRulePackagePublishOptions`, `useFinalizeRulePackageExport` to `useFinalizeRulePackagePublish`, `exportingRulePackage` to `publishingRulePackage`, and `downloadRuleDocument` to `publishRulePackage`. Return exactly `{ publishingRulePackage, publishRulePackage }`. Keep the current local-blocker and workflow-conflict branches, and delete the archive-file array plus `createZipBlob()` and `downloadBlob()` calls.

- [ ] **Step 6: Update the publish dialog copy**

```vue
<h2 id="publish-review-title">审核并发布规则包</h2>
<p>请确认本次规则包的审核结果。确认后将发布规则包，下载可在发布完成后单独进行。</p>
<button
  type="button"
  class="is-primary"
  :disabled="review?.status !== 'ready'"
  @click="confirm"
>
  确认发布
</button>
```

Preserve summary, manual-factor notice, blockers, locate, close, and cancel behavior.

- [ ] **Step 7: Run all publish/review tests**

```powershell
npm.cmd test -- src/composables/useFinalizeRulePackagePublish.spec.ts src/composables/useRulePackagePublishReview.spec.ts src/components/finalize/RulePackagePublishReviewDialog.spec.ts
```

Expected: tests pass with no frontend archive or download dependency in the publish path.

---

### Task 5: Wire the Three Fourth-Step Actions and Current-Package State

**Files:**
- Create: `process-plan-agent-ui/src/utils/finalizeRulePackageActionState.ts`
- Create: `process-plan-agent-ui/src/utils/finalizeRulePackageActionState.spec.ts`
- Modify: `process-plan-agent-ui/src/views/FinalizeView.vue:1-224,304-484,634-639,918-1100,1323-1361,1560-1600`

**Interfaces:**
- Consumes: publish and download composables from Tasks 3 and 4.
- Produces: three action buttons with independent labels and disabled states.
- State source: `currentPublishedPackage: Ref<FinalizedRulePackageResult | null>` plus `outdatedRulePackageVersion`.
- Review handler: `handleRuleReview()` performs parse and safe auto-confirm only.

- [ ] **Step 1: Write failing pure action-state tests**

```typescript
import { describe, expect, it } from 'vitest'
import {
  publishActionLabel,
  reviewActionLabel,
  downloadActionLabel,
  rulePackageActionDisabled,
} from './finalizeRulePackageActionState'

const idle = {
  resetting: false,
  parsing: false,
  reviewing: false,
  publishing: false,
  downloading: false,
  hasSegments: true,
  factorCatalogReady: true,
  hasReviewWork: true,
  allRulesConfirmed: false,
  currentVersion: null,
}

describe('finalizeRulePackageActionState', () => {
  it('uses the confirmed action labels', () => {
    expect(reviewActionLabel(idle, 0, 0)).toBe('规则审核')
    expect(publishActionLabel(idle)).toBe('发布规则包')
    expect(downloadActionLabel(idle)).toBe('下载当前版本')
  })

  it('marks a matching published package as downloadable', () => {
    const state = { ...idle, hasReviewWork: false, allRulesConfirmed: true, currentVersion: 3 }
    expect(reviewActionLabel(state, 0, 0)).toBe('规则已审核')
    expect(publishActionLabel(state)).toBe('已发布 V3')
    expect(rulePackageActionDisabled(state)).toEqual({ review: true, publish: true, download: false })
  })

  it('keeps stale confirmed content publishable but not downloadable', () => {
    const state = { ...idle, hasReviewWork: false, allRulesConfirmed: true, currentVersion: null }
    expect(rulePackageActionDisabled(state)).toEqual({ review: true, publish: false, download: true })
  })
})
```

- [ ] **Step 2: Run the state tests and verify the missing utility failure**

```powershell
npm.cmd test -- src/utils/finalizeRulePackageActionState.spec.ts
```

Expected: test collection fails because the utility does not exist.

- [ ] **Step 3: Implement pure state helpers**

```typescript
export type RulePackageActionState = {
  resetting: boolean
  parsing: boolean
  reviewing: boolean
  publishing: boolean
  downloading: boolean
  hasSegments: boolean
  factorCatalogReady: boolean
  hasReviewWork: boolean
  allRulesConfirmed: boolean
  currentVersion: number | null
}

const busy = (state: RulePackageActionState) => (
  state.resetting || state.parsing || state.reviewing || state.publishing || state.downloading
)

export function reviewActionLabel(state: RulePackageActionState, completed: number, total: number) {
  if (state.parsing) return `正在识别 ${completed}/${total}`
  if (state.reviewing) return `正在审核 ${completed}/${total}`
  if (state.allRulesConfirmed) return '规则已审核'
  return '规则审核'
}

export function publishActionLabel(state: RulePackageActionState) {
  if (state.publishing) return '正在发布...'
  if (state.currentVersion) return `已发布 V${state.currentVersion}`
  return '发布规则包'
}

export function downloadActionLabel(state: RulePackageActionState) {
  return state.downloading ? '正在下载...' : '下载当前版本'
}

export function rulePackageActionDisabled(state: RulePackageActionState) {
  const shared = busy(state) || !state.hasSegments || !state.factorCatalogReady
  return {
    review: shared || !state.hasReviewWork || state.allRulesConfirmed,
    publish: shared || !state.allRulesConfirmed || state.currentVersion !== null,
    download: busy(state) || state.currentVersion === null,
  }
}
```

- [ ] **Step 4: Replace version-only refs with current package metadata**

```typescript
const currentPublishedPackage = ref<FinalizedRulePackageResult | null>(null)
const outdatedRulePackageVersion = ref<number | null>(null)
const lastExportedRulePackageVersion = computed(() => currentPublishedPackage.value?.version || null)
const currentPublishedPackageId = computed(() => currentPublishedPackage.value?.id || null)
```

When loading, assign `latestPackage` to `currentPublishedPackage` only after the existing route-version and content-hash comparison succeeds. When a rule changes, move its version to `outdatedRulePackageVersion` and clear `currentPublishedPackage`.

- [ ] **Step 5: Split the current handler into review-only behavior**

```typescript
async function handleRuleReview() {
  if (reviewingRules.value || batchParsing.value || batchReviewing.value || publishingRulePackage.value) return
  if (!factorCatalogReady.value) {
    factorCatalogError.value ||= '标准因子目录尚未加载，请重试后再进行规则审核。'
    return
  }
  reviewingRules.value = true
  batchNotice.value = ''
  try {
    if (batchEligibleCards.value.length) {
      await handleBatchParseConditions([...batchEligibleCards.value])
      await nextTick()
    }
    if (autoConfirmableReviewCards.value.length) {
      await handleCompleteReview()
      await nextTick()
    }
    const remaining = segmentCards.value.filter(item => (
      finalizeRuleMode(item) !== 'mainline'
      && !hasCurrentConfirmedUserRule(item, factorCatalogVersion.value)
    ))
    onlyPending.value = Boolean(remaining.length)
    if (remaining.length) {
      activeSegmentId.value = remaining[0]?.segment.id || activeSegmentId.value
      batchNotice.value = `系统已自动处理可安全确认的规则；还有 ${remaining.length} 道工序需要人工处理。`
    } else {
      setBatchNotice('规则审核完成。')
    }
  } finally {
    reviewingRules.value = false
  }
}
```

This handler must not call compile, publish, publish-review dialog, or download functions.

- [ ] **Step 6: Wire the publish-only and download-only composables**

Use the full publish options object:

```typescript
const {
  publishingRulePackage,
  publishRulePackage,
} = useFinalizeRulePackagePublish({
  projectId,
  projectName,
  savedRoute,
  segmentCards,
  displayName: finalizeSegmentDisplayName,
  metaLabel: finalizeSegmentMetaLabel,
  phaseLabel: resolveFinalizePhase,
  primarySteps: finalizeSegmentPrimarySteps,
  attachedSteps: finalizeSegmentAttachedSteps,
  conditionFields,
  standardFactors,
  factorCatalogVersion,
  onBlockedCards: async (cards) => {
    onlyPending.value = true
    await requestPublishReview(createBlockedPublishReview(cards))
  },
  onPublishReviewRequired: requestPublishReview,
  onPublished: (packageValue) => {
    currentPublishedPackage.value = packageValue
    outdatedRulePackageVersion.value = null
    setBatchNotice(`规则包 V${packageValue.version} 已发布。`)
  },
  onPublishIssue: issue => {
    rulePackageIssue.value = { ...issue, context: '规则包发布' }
  },
  onWorkflowConflict: () => loadWorkspace(true),
})
```

Wire download independently:

```typescript
const {
  downloadingRulePackage,
  downloadCurrentRulePackage,
} = useFinalizedRulePackageDownload({
  packageId: currentPublishedPackageId,
  packageVersion: lastExportedRulePackageVersion,
  projectName,
  onDownloadIssue: issue => {
    rulePackageIssue.value = { ...issue, context: '规则包下载' }
  },
})
```

- [ ] **Step 7: Replace the compound button with three actions**

Build the state passed to the pure helper before rendering the buttons:

```typescript
const rulePackageActionState = computed(() => ({
  resetting: resettingWorkflow.value,
  parsing: batchParsing.value,
  reviewing: batchReviewing.value || reviewingRules.value,
  publishing: publishingRulePackage.value,
  downloading: downloadingRulePackage.value,
  hasSegments: Boolean(segmentCards.value.length),
  factorCatalogReady: factorCatalogReady.value,
  hasReviewWork: Boolean(batchEligibleCards.value.length || autoConfirmableReviewCards.value.length),
  allRulesConfirmed: allCurrentRulesConfirmed.value,
  currentVersion: lastExportedRulePackageVersion.value,
}))
const actionDisabled = computed(() => rulePackageActionDisabled(rulePackageActionState.value))
const reviewButtonLabel = computed(() => reviewActionLabel(
  rulePackageActionState.value,
  batchParsing.value ? batchParseCompleted.value : batchReviewCompleted.value,
  batchParsing.value ? batchParseTotal.value : batchReviewTotal.value,
))
const publishButtonLabel = computed(() => publishActionLabel(rulePackageActionState.value))
const downloadButtonLabel = computed(() => downloadActionLabel(rulePackageActionState.value))
```

Then replace the compound control:

```vue
<button class="ash-btn-outline" @click="handleRuleReview" :disabled="actionDisabled.review">
  {{ reviewButtonLabel }}
</button>
<button class="ash-btn-primary ash-btn-phase-active" @click="publishRulePackage" :disabled="actionDisabled.publish">
  {{ publishButtonLabel }}
</button>
<button
  class="ash-btn-outline"
  @click="downloadCurrentRulePackage"
  :disabled="actionDisabled.download"
  :title="actionDisabled.download && outdatedRulePackageVersion ? '当前规则已变更，请先重新发布' : '下载当前发布版本'"
>
  {{ downloadButtonLabel }}
</button>
```

Use `@element-plus/icons-vue` review, upload, and download icons if they preserve the existing stable button height. Keep the text labels visible.

- [ ] **Step 8: Rename the dialog usage and update fourth-step copy**

Replace imports and template usage with `RulePackagePublishReviewDialog` and `useRulePackagePublishReview`. Rename `createBlockedExportReview` to `createBlockedPublishReview`, `exportReviewVisible` to `publishReviewVisible`, `requestExportReview` to `requestPublishReview`, and `completeExportReview` to `completePublishReview`. Update navigation copy to:

```typescript
if (readyRuleCount.value < reviewableRuleCount.value) {
  return `还有 ${reviewableRuleCount.value - readyRuleCount.value} 条规则待审核，请先完成规则审核。`
}
if (!allCurrentRulesConfirmed.value) return '存在需要人工处理的规则，请完成规则审核。'
if (outdatedRulePackageVersion.value) return `规则内容已有变化，原规则包 V${outdatedRulePackageVersion.value} 已过期，请重新发布。`
if (!lastExportedRulePackageVersion.value) return '规则审核已完成，可以发布规则包。'
return `规则包 V${lastExportedRulePackageVersion.value} 已发布，可以下载或进入路线生成。`
```

Change the empty-state sentence from “可直接审核并导出” to “可以发布规则包，或切换到全部规则浏览”. Rename issue state from export-specific wording to `rulePackageIssue` with publish/download context.

- [ ] **Step 9: Run focused frontend tests**

```powershell
npm.cmd test -- src/utils/finalizeRulePackageActionState.spec.ts src/composables/useFinalizedRulePackageDownload.spec.ts src/composables/useFinalizeRulePackagePublish.spec.ts src/composables/useRulePackagePublishReview.spec.ts src/components/finalize/RulePackagePublishReviewDialog.spec.ts
```

Expected: all focused frontend tests pass.

- [ ] **Step 10: Run TypeScript and production build checks**

```powershell
npm.cmd run build
```

Expected: `vue-tsc -b` and `vite build` exit successfully with no old import paths.

---

### Task 6: Full Regression and Visual Verification

**Files:**
- Verify only; modify implementation files only when a failing check identifies a requirement gap.

**Interfaces:**
- Consumes all previous tasks.
- Produces backend, frontend, and responsive-layout verification evidence.

- [ ] **Step 1: Run backend rule package regression tests**

From `process-plan-agent-api`:

```powershell
..\.runtime\python\python.exe -m pytest tests/test_rule_package_archive.py tests/test_rule_package_api.py tests/test_rule_package_lifecycle.py tests/test_kmai_rule_package_export.py -v
```

Expected: all selected backend tests pass.

- [ ] **Step 2: Run the full frontend test suite**

From `process-plan-agent-ui`:

```powershell
npm.cmd test
```

Expected: all Vitest files pass.

- [ ] **Step 3: Run the production build after the full test run**

```powershell
npm.cmd run build
```

Expected: TypeScript and Vite build succeed.

- [ ] **Step 4: Search for stale compound-action implementation references**

From the repository root:

```powershell
rg -n "审核并导出规则包|确认导出|handleReviewAndExport|downloadRuleDocument|useFinalizeRulePackageExport|RulePackageExportReviewDialog" process-plan-agent-ui/src
```

Expected: no matches.

- [ ] **Step 5: Start the local API and UI on unused ports**

Start from each application directory:

```powershell
..\.runtime\python\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
npm.cmd run dev -- --host 127.0.0.1 --port 5173
```

If a port is occupied, choose the next available port and set the UI API base to the selected API port.

- [ ] **Step 6: Verify the real fourth-step workflow at desktop and mobile widths**

- Buttons read `规则审核`, `发布规则包`, and `下载当前版本`.
- Buttons and progress labels do not overlap metadata, filter, or refresh controls.
- Rule review completes without opening the publish dialog.
- Publish opens “审核并发布规则包”, creates one version, and does not download.
- Repeated download retrieves the same version without creating another version.
- Editing a rule clears current-package state, disables download, and permits a new publish after review.
- The ZIP opens and contains all expected V2 and `kmai-v1` files.

- [ ] **Step 7: Inspect the final working diff without committing**

```powershell
git status --short
git diff --check
git diff --stat
```

Expected: only planned backend, frontend, test, design, and plan files changed; the whitespace check is clean.
