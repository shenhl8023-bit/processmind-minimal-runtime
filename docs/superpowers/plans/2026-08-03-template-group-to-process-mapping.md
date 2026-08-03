# 模板分组到工序工步映射 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将模板映射工作台改为“叶子分组 → 加工工序 → 工步”的审核流程，减少无关工步审核并保留可追溯的多对多关系。

**Architecture:** 保持 `step_mappings_json` 的 `confirmed` 记录作为“叶子分组—工步”关系，只在前端反向按叶子索引并编辑。新增纯前端资格分类器默认隐藏非几何加工工步；现有工步建议接口增加 `target_group_id`，让受控候选和模型排序只服务当前叶子分组。

**Tech Stack:** Vue 3 Composition API、TypeScript、Vitest、FastAPI、Pydantic、SQLAlchemy、pytest。

## Global Constraints

- 正式目标只能是具有合法特征选择的模板叶子；父分组仅导航与汇总。
- 叶子和工步允许多对多；同一叶子—工步关系去重。
- 默认仅展示几何加工工步；“其它工步”收起后仍允许用户手动加入。
- 未配置叶子允许保存，只显示汇总提示；不再要求处理每一个工步。
- 保存时只提交 `confirmed`；不再生成批量 `not_applicable` 记录。
- 模型只能在当前叶子的程序候选工步中排序，不能创建分组、特征、工序或工步。
- 不修改 Kmsoft XML、规则包格式或 KMAI 代码。

---

### Task 1: 建立工步资格与叶子反向索引领域模型

**Files:**
- Create: `process-plan-agent-ui/src/composables/templateGroupProcessMapping.ts`
- Create: `process-plan-agent-ui/src/composables/templateGroupProcessMapping.spec.ts`
- Modify: `process-plan-agent-ui/src/composables/templateStepMapping.ts`
- Modify: `process-plan-agent-ui/src/composables/templateStepMapping.spec.ts`

**Interfaces:**
- Consumes: `TemplateOperation`、`TemplateStepRef`、`GroupTemplateNode`、`GroupTemplateStepMappingInput`。
- Produces: `TemplateProcessStep`、`buildEligibleTemplateSteps()`、`groupConfirmedMappingsByLeaf()`、`featureLeafConfiguration()`、`confirmedTemplateStepMappings()`。

- [ ] **Step 1: 写失败测试**

在 `templateGroupProcessMapping.spec.ts` 添加固定工序夹具，并写入：

```ts
it('keeps geometry-processing steps and excludes non-feature steps in one operation', () => {
  const result = buildEligibleTemplateSteps([{
    id: 11,
    name: '复合加工',
    step_items: ['钻孔', '清洗零件', '检查孔径', '倒角'],
  }])
  expect(result.eligible.map(item => item.step_name)).toEqual(['钻孔', '倒角'])
  expect(result.excluded.map(item => item.step_name)).toEqual(['清洗零件', '检查孔径'])
})

it('indexes one step under more than one feature leaf', () => {
  const result = groupConfirmedMappingsByLeaf([outerSlotMapping, innerSlotMapping], tree)
  expect(result.grp_outer).toHaveLength(1)
  expect(result.grp_inner).toHaveLength(1)
  expect(result.grp_outer[0]!.source_step_key).toBe(result.grp_inner[0]!.source_step_key)
})

it('allows an unconfigured feature leaf', () => {
  expect(featureLeafConfiguration(tree, [holeMapping]).unconfigured.map(item => item.key))
    .toEqual(['grp_end'])
})
```

在 `templateStepMapping.spec.ts` 写入：

```ts
it('filters legacy skipped rows out of the next formal save', () => {
  expect(confirmedTemplateStepMappings([confirmedMapping, skippedMapping]))
    .toEqual([confirmedMapping])
})
```

- [ ] **Step 2: 验证 RED**

Run:

```bash
cd process-plan-agent-ui
npm test -- src/composables/templateGroupProcessMapping.spec.ts src/composables/templateStepMapping.spec.ts
```

Expected: FAIL，因为领域模块和保存筛选函数尚未定义。

- [ ] **Step 3: 实现资格分类和反向索引**

在新模块定义：

```ts
export type TemplateStepEligibility = 'eligible' | 'excluded'

export type TemplateProcessStep = TemplateStepRef & {
  eligibility: TemplateStepEligibility
  eligibility_reason: string
}

export function buildEligibleTemplateSteps(operations: TemplateOperation[]): {
  eligible: TemplateProcessStep[]
  excluded: TemplateProcessStep[]
}

export function groupConfirmedMappingsByLeaf(
  mappings: GroupTemplateStepMappingInput[],
  tree: GroupTemplateNode[],
): Record<string, GroupTemplateStepMappingInput[]>

export function featureLeafConfiguration(
  tree: GroupTemplateNode[],
  mappings: GroupTemplateStepMappingInput[],
): { configured: GroupTemplateNode[]; unconfigured: GroupTemplateNode[] }
```

使用集中化词表：

```ts
const EXCLUDED_STEP_PATTERNS = [
  /热处理|调质|正常化|正火|淬火|回火|退火|时效|清洗|除油|检验|检查|探伤|测量|包装|标记|打标|装配/,
]
const GEOMETRY_PROCESS_PATTERNS = [
  /车|铣|钻|镗|铰|攻丝|磨|研|珩|切槽|挖槽|倒角|倒圆|成形|割型|打型|电火花|线切割/,
]
```

先匹配排除动作，再匹配加工动作；“孔、槽、面”等名词不能单独构成加工判定。反向索引只保留合法模板叶子上的 `confirmed` 记录。

在 `templateStepMapping.ts` 增加：

```ts
export function confirmedTemplateStepMappings(
  mappings: GroupTemplateStepMappingInput[],
): GroupTemplateStepMappingInput[] {
  return mappings.filter(item => item.status === 'confirmed' && item.template_group_path.length > 0)
}
```

保留旧 `not_applicable` 读取兼容，但新工作台不调用 `createNotApplicableStepMapping()`。

- [ ] **Step 4: 验证 GREEN**

Run:

```bash
cd process-plan-agent-ui
npm test -- src/composables/templateGroupProcessMapping.spec.ts src/composables/templateStepMapping.spec.ts
```

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add process-plan-agent-ui/src/composables/templateGroupProcessMapping.ts process-plan-agent-ui/src/composables/templateGroupProcessMapping.spec.ts process-plan-agent-ui/src/composables/templateStepMapping.ts process-plan-agent-ui/src/composables/templateStepMapping.spec.ts
git diff --cached --check
git commit -m "feat: classify template process steps"
```

### Task 2: 将建议接口限定为当前叶子分组

**Files:**
- Modify: `process-plan-agent-api/app/schemas/schemas.py`
- Modify: `process-plan-agent-api/app/services/template_group_mapping.py`
- Modify: `process-plan-agent-api/tests/test_template_group_mapping.py`
- Modify: `process-plan-agent-ui/src/api/extract.ts`

**Interfaces:**
- Consumes: 已确认模板树、现有 `TemplateStepMappingSuggestRequest`。
- Produces: 可选 `target_group_id`，并保证响应候选只能来自该合法叶子。

- [ ] **Step 1: 写失败测试**

在 `test_template_group_mapping.py` 添加：

```python
@pytest.mark.asyncio
async def test_step_suggestions_scope_candidates_to_target_leaf(mapping_store, monkeypatch):
    sessions, tree = mapping_store
    hole_key = _node_key(tree, ["A侧", "孔"])

    async def unavailable(*args, **kwargs):
        raise RuntimeError("offline")

    monkeypatch.setattr(template_group_mapping, "call_llm", unavailable)
    async with sessions() as db:
        result = await template_group_mapping.resolve_template_step_mappings(
            db,
            TemplateStepMappingSuggestRequest(
                project_id=7,
                expected_template_revision=1,
                target_group_id=hole_key,
                operations=[TemplateGroupMappingOperationIn(
                    operation_id=1,
                    operation_name="车削加工（A侧）",
                    step_items=["钻孔", "车外圆"],
                )],
            ),
        )

    assert [item.group_id for item in result.suggestions[0].candidates] == [hole_key]
    assert result.suggestions[1].candidates == []
    assert result.model_used is False
```

增加目标为父分组或不存在 ID 时 `422` 的测试。

- [ ] **Step 2: 验证 RED**

Run:

```bash
cd process-plan-agent-api
.venv/bin/python -m pytest tests/test_template_group_mapping.py -q
```

Expected: FAIL，因为请求模型没有 `target_group_id`。

- [ ] **Step 3: 扩展请求合约**

在后端和前端同名请求类型增加：

```python
target_group_id: Optional[str] = Field(default=None, min_length=1, max_length=128)
```

```ts
target_group_id?: string
```

字段可选，旧调用保持不变。

- [ ] **Step 4: 验证叶子并收窄候选**

在 `resolve_template_step_mappings()` 中序列化模板树后加入：

```python
target_id = _clean_text(body.target_group_id)
allowed_group_ids: set[str] | None = None
if target_id:
    target = next((node for node in _flatten_template_nodes(tree) if node.get("key") == target_id), None)
    if target is None or not is_feature_mapping_target(target):
        raise HTTPException(422, "智能推荐目标必须是具有合法特征的叶子分组。")
    allowed_group_ids = {target_id}

prepared = [
    (step, [candidate for candidate in candidates if not allowed_group_ids or candidate.group_id in allowed_group_ids])
    for operation in body.operations
    for step, candidates in prepare_step_candidates(operation, tree)
]
```

继续使用现有模型约束“只能从 candidates 选择”。当前叶子不是程序候选时返回空候选，模型不能凭名称补造关系。

- [ ] **Step 5: 验证接口**

Run:

```bash
cd process-plan-agent-api
.venv/bin/python -m pytest tests/test_template_group_mapping.py -q
```

Expected: PASS，已有工步建议回归测试和范围限定测试都通过。

- [ ] **Step 6: 提交**

```bash
git add process-plan-agent-api/app/schemas/schemas.py process-plan-agent-api/app/services/template_group_mapping.py process-plan-agent-api/tests/test_template_group_mapping.py process-plan-agent-ui/src/api/extract.ts
git diff --cached --check
git commit -m "feat: scope template suggestions by leaf group"
```

### Task 3: 在树上展示叶子配置状态

**Files:**
- Modify: `process-plan-agent-ui/src/components/extract/TemplateGroupTreeNode.vue`
- Modify: `process-plan-agent-ui/src/composables/templateGroupProcessMapping.spec.ts`

**Interfaces:**
- Consumes: `configuredLeafKeys`、`unconfiguredLeafKeys` 和 `mappedCounts`。
- Produces: 父分组汇总，叶子“已配置/未配置”状态；父分组不再是映射目标。

- [ ] **Step 1: 写状态测试**

```ts
it('marks only legal feature leaves as configured or unconfigured', () => {
  const state = featureLeafConfiguration(tree, [holeMapping])
  expect(state.configured.map(item => item.key)).toEqual(['grp_hole'])
  expect(state.unconfigured.map(item => item.key)).toEqual(['grp_end'])
})
```

- [ ] **Step 2: 改造树组件**

新增 props：

```ts
configuredLeafKeys?: string[]
unconfiguredLeafKeys?: string[]
mappedCounts?: Record<string, number>
```

叶子渲染：

```vue
<span v-if="featureLeaf && configuredLeafKeys.includes(node.key)" class="tgtn-status is-configured">
  已配置 {{ mappedCount }}
</span>
<span v-else-if="featureLeaf" class="tgtn-status is-unconfigured">未配置</span>
```

父分组保持展开和范围标签，但点击只进行导航与后代统计；删除 `clear` 事件和“范围内识别”的含义。

- [ ] **Step 3: 验证**

Run:

```bash
cd process-plan-agent-ui
npm test -- src/composables/templateGroupProcessMapping.spec.ts
```

Expected: PASS。

- [ ] **Step 4: 提交**

```bash
git add process-plan-agent-ui/src/components/extract/TemplateGroupTreeNode.vue process-plan-agent-ui/src/composables/templateGroupProcessMapping.spec.ts
git diff --cached --check
git commit -m "feat: show template leaf configuration state"
```

### Task 4: 将映射弹窗改造成分组主导工作台

**Files:**
- Modify: `process-plan-agent-ui/src/components/extract/TemplateGroupMappingDialog.vue`
- Modify: `process-plan-agent-ui/src/composables/templateGroupProcessMapping.ts`
- Modify: `process-plan-agent-ui/src/composables/templateGroupProcessMapping.spec.ts`

**Interfaces:**
- Consumes: 资格分类、按叶子反向索引、单叶建议接口。
- Produces: 叶子选择、当前叶子的加工工步勾选、可选智能建议、未配置提示和仅保存 `confirmed` 的映射工作台。

- [ ] **Step 1: 写当前叶子增删关系测试**

在领域模块提供：

```ts
export function removeLeafMapping(
  mappings: Record<string, GroupTemplateStepMappingInput>,
  leafKey: string,
  tree: GroupTemplateNode[],
): Record<string, GroupTemplateStepMappingInput>
```

测试：

```ts
it('removes one leaf edge without removing another leaf edge from the same step', () => {
  const draft = mappingRecord([outerSlotMapping, innerSlotMapping])
  const result = removeLeafMapping(draft, 'grp_outer', tree)
  expect(Object.values(result).map(item => item.template_group_path)).toEqual([['A侧', '内环槽']])
})
```

- [ ] **Step 2: 替换弹窗状态**

删除以下状态和方法：

```ts
selectedStepKeys
unresolvedSteps
activeTargets
recognizeAllSteps
markStepNotApplicable
applyActiveTarget
```

新增：

```ts
const classifiedSteps = computed(() => buildEligibleTemplateSteps(props.operations))
const activeLeaf = computed(() => model.template.value
  ? findTemplateGroupByKey(model.template.value.tree, activeGroupKey.value)
  : null)
const mappingsByLeaf = computed(() => groupConfirmedMappingsByLeaf(
  Object.values(draftStepMappings.value),
  model.template.value?.tree || [],
))
const activeLeafStepKeys = computed(() => new Set(
  (activeLeaf.value && isFeatureLeaf(activeLeaf.value)
    ? mappingsByLeaf.value[activeLeaf.value.key] || []
    : []
  ).map(item => item.source_step_key),
))
const leafConfiguration = computed(() => featureLeafConfiguration(
  model.template.value?.tree || [],
  Object.values(draftStepMappings.value),
))
```

打开模板时选择第一个合法叶子。父分组被选中时右侧只显示其后代配置汇总和“请选择一个叶子分组进行编辑”。

- [ ] **Step 3: 替换模板结构和文案**

将顶部进度改为：

```vue
<div class="tgmd-group-progress">
  已配置 {{ leafConfiguration.configured.length }} /
  {{ leafConfiguration.configured.length + leafConfiguration.unconfigured.length }} 个叶子分组
</div>
```

右侧标题、特征和建议按钮：

```vue
<h3>关联加工工序</h3>
<span>{{ activeLeaf?.path.join(' / ') || '请选择叶子分组' }}</span>
<p v-if="activeLeaf && isFeatureLeaf(activeLeaf)" class="tgmd-feature-summary">
  特征选择：{{ activeLeaf.feature_selections.join('、') }}
</p>
<button class="tgmd-smart-button" :disabled="!activeLeaf || !isFeatureLeaf(activeLeaf) || recognizing" @click="suggestActiveLeaf">
  <MagicStick />{{ recognizing ? '正在推荐' : '智能推荐当前分组' }}
</button>
```

每个可见加工工步用单个复选框编辑当前叶子的关联。删除中间箭头、黄色“待处理”行、每工步“不依赖模板特征”、全量识别按钮和“已处理 X/Y 工步”。右侧底部增加“显示其它工步”，默认收起 `classifiedSteps.excluded`，展开后可建立正式关联。

- [ ] **Step 4: 实现当前叶子映射与单叶建议**

```ts
function toggleActiveLeafStep(step: TemplateStepRef) {
  if (!activeLeaf.value || !isFeatureLeaf(activeLeaf.value)) return
  const mapping = createTemplateStepMapping(step, activeLeaf.value, activeLeaf.value.path.slice(0, -1))
  const key = stepMappingKey(mapping)
  if (draftStepMappings.value[key]) delete draftStepMappings.value[key]
  else draftStepMappings.value[key] = mapping
  persistStepDraft()
}

async function suggestActiveLeaf() {
  if (!activeLeaf.value || !isFeatureLeaf(activeLeaf.value)) return
  const response = await suggestTemplateStepMappings({
    project_id: props.projectId,
    expected_template_revision: model.templateRevision.value,
    target_group_id: activeLeaf.value.key,
    operations: activeLeafOperations.value.map(operation => ({
      operation_id: operationId(operation),
      operation_name: operation.name,
      step_items: eligibleStepsForOperation(operation).map(step => step.step_name),
      rule_evidence: [],
      rule_reasons: [],
    })),
  })
  // 仅把 recommended_group_ids 包含 activeLeaf.key 且 confidence >= 0.90 的工步加入草稿。
}
```

建议失败仅设置 `mappingWarnings`，不得修改草稿。建议不能删除任何用户已选择的关系。

- [ ] **Step 5: 改造保存**

```ts
async function saveStepMappings() {
  const confirmed = confirmedTemplateStepMappings(Object.values(draftStepMappings.value))
  const { unconfigured } = featureLeafConfiguration(model.template.value?.tree || [], confirmed)
  if (unconfigured.length) {
    mappingWarnings.value = [`仍有 \${unconfigured.length} 个叶子分组未配置，已按当前映射保存。`]
  }
  model.draftStepMappings.value = confirmed
  await model.saveStepMappings()
  if (!model.error.value && model.template.value) {
    clearTemplateStepMappingDraft(props.projectId)
    emit('save', { stepMappings: model.template.value.step_mappings || [], templateRevision: model.templateRevision.value })
    closeDialog()
  }
}
```

保存按钮不因未配置叶子禁用；修订冲突或网络失败时保留草稿并显示现有错误。

- [ ] **Step 6: 验证前端工作台**

Run:

```bash
cd process-plan-agent-ui
npm test -- src/composables/templateGroupProcessMapping.spec.ts src/composables/templateStepMapping.spec.ts src/composables/useProjectGroupTemplate.spec.ts
npm run build
```

Expected: PASS。

- [ ] **Step 7: 提交**

```bash
git add process-plan-agent-ui/src/components/extract/TemplateGroupMappingDialog.vue process-plan-agent-ui/src/composables/templateGroupProcessMapping.ts process-plan-agent-ui/src/composables/templateGroupProcessMapping.spec.ts
git diff --cached --check
git commit -m "feat: map template groups to process steps"
```

### Task 5: 修正入口计数并完成回归验收

**Files:**
- Modify: `process-plan-agent-ui/src/views/ExtractView.vue`
- Modify: `process-plan-agent-ui/src/components/extract/ExtractRouteShellHeader.vue`
- Modify: `process-plan-agent-ui/src/composables/templateGroupProcessMapping.spec.ts`
- Verify: `process-plan-agent-api/tests`

**Interfaces:**
- Consumes: 保存后的 `confirmed` 映射。
- Produces: 第二步入口只显示真实分组—工步关系数量，历史跳过项不计数。

- [ ] **Step 1: 写入口计数测试**

```ts
it('counts only confirmed group-to-step edges for the route header', () => {
  expect(confirmedTemplateStepMappings([confirmedMapping, skippedMapping])).toEqual([confirmedMapping])
})
```

- [ ] **Step 2: 更新入口计数**

在 `ExtractView.vue` 使用：

```ts
const templateStepMappingCount = computed(() => confirmedTemplateStepMappings(
  projectGroupTemplate.template.value?.step_mappings || [],
).length)
```

保留第二步归并未完成时禁用模板映射入口的现有行为。

- [ ] **Step 3: 全量自动化验证**

Run:

```bash
cd process-plan-agent-api
.venv/bin/python -m pytest -q
cd ../process-plan-agent-ui
npm test
npm run build
cd ..
git diff --check
```

Expected: API、Vitest、类型检查和生产构建全部通过。

- [ ] **Step 4: 浏览器验收**

1. 完成第二步归并后打开模板映射，确认顶部显示叶子分组配置进度。
2. 选择 `A侧 / 孔`，确认右侧默认只显示加工候选，调质、正常化、检验不出现。
3. 勾选钻孔、镗孔、铰孔，切换叶子再返回，确认草稿保留。
4. 将同一车槽工步关联外环槽和内环槽，确认两个叶子均显示已配置。
5. 保持一个叶子未配置，确认保存可用并显示汇总提示。
6. 关闭重开确认服务端恢复；更换 XML 和第二步重推后确认既有失效逻辑仍生效。

- [ ] **Step 5: 提交**

```bash
git add process-plan-agent-ui/src/views/ExtractView.vue process-plan-agent-ui/src/components/extract/ExtractRouteShellHeader.vue process-plan-agent-ui/src/composables/templateGroupProcessMapping.spec.ts
git diff --cached --check
git commit -m "fix: report confirmed group process mappings"
```

### Task 6: 计划自检与提交

**Files:**
- Create: `docs/superpowers/plans/2026-08-03-template-group-to-process-mapping.md`

**Interfaces:**
- Consumes: 已确认设计文档。
- Produces: 可复现的实施记录，明确不包含 KMAI 改动。

- [ ] **Step 1: 检查设计覆盖**

确认任务分别覆盖：分组主导关系、加工筛选、叶子状态、当前叶子推荐、未配置可保存、草稿失效、模型失败回退、服务端叶子验证和浏览器验收。

- [ ] **Step 2: 扫描占位内容**

Run:

```bash
scan_pattern="$(printf '%s' 'TO''DO|TB''D|implement'' later|fill in'' details|待''定|稍''后')"
rg -n "$scan_pattern" docs/superpowers/plans/2026-08-03-template-group-to-process-mapping.md
```

Expected: 无输出。

- [ ] **Step 3: 提交计划**

```bash
git add docs/superpowers/plans/2026-08-03-template-group-to-process-mapping.md
git diff --cached --check
git commit -m "docs: plan group-to-process mapping"
```
