<script setup lang="ts">
import { computed } from 'vue'
import type { KnowledgeGuidance, KnowledgeGuidanceMetric, KnowledgeSource } from '@/api/knowledge'

const props = defineProps<{ guidance: KnowledgeGuidance }>()

const isRoute = computed(() => props.guidance.kind === 'route' || props.guidance.kind === 'stage_overview')
const verificationLabels = { verified: '已核对原文', pending: '待核对', conflict: '存在冲突' }
const operationLabels = { required: '必选', conditional: '按需', virtual: '虚拟', unspecified: '未说明' }
const resourceLabels = { equipment: '设备', tool: '刀具', gauge: '量具', fixture: '工装夹具' }

function metricRange(metric: KnowledgeGuidanceMetric): string {
  const lower = metric.min != null && Number.isFinite(metric.min) ? String(metric.min) : ''
  const upper = metric.max != null && Number.isFinite(metric.max) ? String(metric.max) : ''
  const value = lower && upper ? lower === upper ? lower : `${lower}–${upper}` : lower || upper
  return value ? `${value}${metric.unit ? ` ${metric.unit}` : ''}` : '数值未提供'
}

function sourceLocation(source: KnowledgeSource): string {
  return [
    source.document_name,
    source.worksheet,
    source.row_no != null ? `第 ${source.row_no} 行` : '',
    source.cell_range,
    source.page_no != null ? `第 ${source.page_no} 页` : '',
    source.identity,
  ].filter(Boolean).join(' · ') || '来源定位未提供'
}
</script>

<template>
  <section class="guidance-panel" :aria-label="isRoute ? '典型路线结构化信息' : '工艺说明结构化信息'">
    <div class="guidance-heading">
      <div>
        <h4>{{ isRoute ? '典型路线' : '工艺说明' }}</h4>
        <p v-if="guidance.completeness === 'stage_overview'">阶段概要，不能据此认定完整工序路线</p>
        <p v-else-if="isRoute">典型指导步骤，不代表历史执行记录</p>
        <p v-else>结合适用范围与前提理解原文要求</p>
      </div>
      <span class="guidance-status" :class="`guidance-status-${guidance.verification_status}`">{{ verificationLabels[guidance.verification_status] || '待核对' }}</span>
    </div>

    <div class="guidance-scope">
      <span v-if="guidance.applicability"><b>适用范围</b>{{ guidance.applicability }}</span>
      <span v-if="guidance.part_family"><b>零件类别</b>{{ guidance.part_family }}</span>
      <span v-if="guidance.typical_part"><b>典型零件</b>{{ guidance.typical_part }}</span>
      <span v-if="guidance.materials?.length"><b>材料 / 状态</b>{{ guidance.materials.join('、') }}</span>
      <span v-if="guidance.topics?.length"><b>工艺主题</b>{{ guidance.topics.join('、') }}</span>
    </div>

    <dl class="guidance-rule">
      <div v-if="guidance.conditions"><dt>前提条件</dt><dd>{{ guidance.conditions }}</dd></div>
      <div v-if="guidance.conclusion"><dt>要求 / 结论</dt><dd>{{ guidance.conclusion }}</dd></div>
      <div v-if="guidance.exceptions"><dt>例外与限制</dt><dd>{{ guidance.exceptions }}</dd></div>
    </dl>

    <div v-if="guidance.metrics?.length" class="guidance-metrics" aria-label="指标与口径">
      <div v-for="(metric, index) in guidance.metrics" :key="`${metric.name}-${index}`" class="guidance-metric">
        <span>{{ metric.name }}</span>
        <strong>{{ metricRange(metric) }}</strong>
        <small v-if="metric.basis">{{ metric.basis }}</small>
        <small v-if="metric.direction">{{ metric.direction }}</small>
      </div>
    </div>

    <div v-if="guidance.operations?.length" class="guidance-route">
      <div class="guidance-section-heading">
        <h5>典型步骤</h5>
        <span>{{ guidance.completeness === 'verified_sequence' ? '已核对步骤顺序' : '阶段概要' }} · {{ guidance.operations.length }} 项</span>
      </div>
      <ol class="guidance-operations" aria-label="典型指导步骤">
        <li v-for="operation in guidance.operations" :key="operation.id" class="guidance-operation">
          <div class="guidance-operation-heading">
            <span class="guidance-operation-number">{{ operation.number || operation.sequence }}</span>
            <strong>{{ operation.name }}</strong>
            <span class="guidance-operation-status" :class="`operation-${operation.execution_status}`">{{ operationLabels[operation.execution_status] || '未说明' }}</span>
          </div>
          <p v-if="operation.condition" class="guidance-operation-condition">{{ operation.condition }}</p>
          <details class="guidance-operation-source">
            <summary>来源依据</summary>
            <p>{{ sourceLocation(operation.source) }}</p>
          </details>
        </li>
      </ol>
    </div>

    <div v-if="guidance.resources?.length" class="guidance-resources">
      <div class="guidance-section-heading"><h5>原文工序资源</h5><span>仅表示原文记录，未自动关联主数据</span></div>
      <div v-for="(resource, index) in guidance.resources" :key="`${resource.name}-${index}`" class="guidance-resource">
        <span class="guidance-resource-kind">{{ resourceLabels[resource.category] || '资源' }}</span>
        <div>
          <strong>{{ resource.name }}</strong>
          <p v-if="resource.model">型号 / 规格：{{ resource.model }}</p>
          <p v-if="resource.identifier">图号 / 标识：{{ resource.identifier }}</p>
          <p v-if="resource.basis">关联依据：{{ resource.basis }}</p>
        </div>
      </div>
    </div>

    <p v-if="guidance.kind === 'formula'" class="guidance-formula-note">公式仅供原文解释，须结合变量定义与适用对象理解，不提供自动计算。</p>
    <details v-if="guidance.original_excerpt" class="guidance-excerpt">
      <summary>查看原文摘录</summary>
      <p>{{ guidance.original_excerpt }}</p>
    </details>
    <p class="guidance-verification-note" :class="{ 'guidance-verification-warning': guidance.verification_status !== 'verified' }" role="status">
      <template v-if="guidance.verification_status === 'conflict'">相关资料存在未解决冲突，请并列核对来源，暂无足够依据确定。</template>
      <template v-else-if="guidance.verification_status === 'pending'">提取内容或步骤顺序尚待核对，不能据此形成确定结论。</template>
      <template v-else>“已核对原文”仅表示提取与原文一致。</template>
      不代表文件现行有效或业务批准。
    </p>
  </section>
</template>

<style scoped>
.guidance-panel { margin: 14px 0 18px; border: 1px solid #dbe4f0; border-radius: 8px; overflow: hidden; color: var(--text-primary); }
.guidance-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; padding: 12px 14px; background: #f7faff; }
.guidance-heading h4 { font-size: 14px; font-weight: 650; }
.guidance-heading p { margin-top: 4px; font-size: 12px; line-height: 1.6; color: var(--text-secondary); }
.guidance-status { flex-shrink: 0; border-radius: 4px; padding: 3px 7px; font-size: 12px; line-height: 1.5; }
.guidance-status-verified { color: #047857; background: #ecfdf5; }
.guidance-status-pending { color: #92400e; background: #fef3c7; }
.guidance-status-conflict { color: #be123c; background: #ffe4e6; }
.guidance-scope { display: flex; flex-wrap: wrap; gap: 6px 18px; padding: 10px 14px; border-top: 1px solid #e5ebf3; border-bottom: 1px solid #e5ebf3; background: #fbfdff; }
.guidance-scope span { display: inline-flex; gap: 7px; font-size: 13px; line-height: 1.7; overflow-wrap: anywhere; }
.guidance-scope b { flex-shrink: 0; color: var(--text-secondary); font-weight: 500; }
.guidance-rule { margin: 0; padding: 6px 14px; }
.guidance-rule > div { display: grid; grid-template-columns: 70px minmax(0, 1fr); gap: 12px; padding: 8px 0; font-size: 13px; line-height: 1.8; }
.guidance-rule > div + div { border-top: 1px solid var(--border-light); }
.guidance-rule dt { color: var(--text-secondary); font-size: 12px; }
.guidance-rule dd { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; }
.guidance-metrics { display: flex; flex-wrap: wrap; gap: 8px; padding: 4px 14px 14px; }
.guidance-metric { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 10px; padding: 9px 11px; border: 1px solid #dbe4f0; border-radius: 6px; background: #f7faff; font-size: 12px; }
.guidance-metric > span { color: var(--text-secondary); }
.guidance-metric strong { color: var(--accent); font-size: 14px; font-weight: 650; font-variant-numeric: tabular-nums; }
.guidance-metric small { color: var(--text-secondary); font-size: 12px; }
.guidance-route, .guidance-resources { border-top: 1px solid var(--border-light); padding: 12px 14px; }
.guidance-section-heading { display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap; gap: 5px 12px; }
.guidance-section-heading h5 { font-size: 12px; font-weight: 650; }
.guidance-section-heading > span { color: var(--text-secondary); font-size: 12px; }
.guidance-operations { list-style: none; margin: 6px 0 0; padding: 0; }
.guidance-operation { padding: 9px 0; border-bottom: 1px solid var(--border-light); }
.guidance-operation:last-child { border-bottom: 0; padding-bottom: 0; }
.guidance-operation-heading { display: flex; align-items: baseline; gap: 10px; font-size: 13px; line-height: 1.7; }
.guidance-operation-number { min-width: 25px; color: var(--accent); font-size: 12px; font-family: ui-monospace, SFMono-Regular, monospace; }
.guidance-operation-heading strong { font-weight: 600; overflow-wrap: anywhere; }
.guidance-operation-status { margin-left: auto; flex-shrink: 0; padding: 1px 6px; border-radius: 4px; font-size: 12px; color: #64748b; background: #f1f5f9; }
.operation-conditional { color: #92400e; background: #fffbeb; }
.operation-virtual { color: #1d4ed8; background: #eff6ff; border: 1px dashed #bfdbfe; }
.operation-required { color: #047857; background: #ecfdf5; }
.guidance-operation-condition { margin: 4px 0 0 35px; font-size: 13px; line-height: 1.7; color: var(--text-secondary); white-space: pre-wrap; }
.guidance-operation-source { margin: 4px 0 0 35px; font-size: 13px; line-height: 1.7; color: var(--text-secondary); }
.guidance-operation-source p { margin-top: 4px; overflow-wrap: anywhere; }
.guidance-resource { display: flex; align-items: baseline; gap: 12px; margin-top: 10px; font-size: 13px; line-height: 1.7; }
.guidance-resource-kind { min-width: 48px; color: var(--text-secondary); font-size: 12px; }
.guidance-resource strong { font-weight: 500; }
.guidance-resource p { color: var(--text-secondary); font-size: 12px; overflow-wrap: anywhere; }
.guidance-formula-note { padding: 0 14px 10px; color: var(--text-secondary); font-size: 13px; line-height: 1.8; }
.guidance-excerpt { padding: 10px 14px; border-top: 1px solid var(--border-light); font-size: 13px; line-height: 1.8; }
.guidance-excerpt p { margin: 7px 0 0; max-height: 240px; overflow-y: auto; padding: 9px 11px; border-radius: 5px; background: #f8fafc; color: var(--text-secondary); white-space: pre-wrap; overflow-wrap: anywhere; }
summary { width: fit-content; color: var(--accent); cursor: pointer; }
summary:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; border-radius: 2px; }
.guidance-verification-note { padding: 9px 14px; border-top: 1px solid var(--border-light); background: #f8fafc; color: var(--text-secondary); font-size: 13px; line-height: 1.8; }
.guidance-verification-warning { background: #fffbeb; color: #92400e; }
@media (max-width: 640px) {
  .guidance-heading, .guidance-scope, .guidance-rule, .guidance-route, .guidance-resources, .guidance-excerpt { padding-left: 11px; padding-right: 11px; }
  .guidance-rule > div { grid-template-columns: 1fr; gap: 2px; }
  .guidance-operation-heading { gap: 7px; }
}
</style>
