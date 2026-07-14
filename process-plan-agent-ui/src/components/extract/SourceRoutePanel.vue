<template>
  <div class="srp-root">

    <!-- ── 面板头部 ── -->
    <div class="srp-head">
      <div class="srp-head-left">
        <span class="srp-head-title">原始全集工序</span>
        <span class="srp-head-sub">未归并 · 证据池</span>
      </div>
    </div>

    <!-- ── 内容滚动区 ── -->
    <div class="srp-scroll" v-if="sections.length">
      <section
        v-for="section in sections"
        :key="section.key"
        class="srp-section"
      >
        <!-- 段组标题 -->
        <div class="srp-section-header">
          <div class="srp-section-info">
            <span class="srp-section-kicker">{{ section.kicker }}</span>
            <span class="srp-section-name">{{ section.title }}</span>
          </div>
        </div>

        <!-- 时间轴工序列表 -->
        <div class="srp-timeline">
          <div
            v-for="(operation, idx) in section.operations"
            :key="operationDisplayKey(operation)"
            class="srp-item-wrap"
          >
            <!-- 轨道：圆点 + 竖线 -->
            <div class="srp-track">
              <div
                class="srp-dot"
                :class="{ 'srp-dot--active': isOpActive(operation) }"
              ></div>
              <div
                v-if="Number(idx) < section.operations.length - 1"
                class="srp-line"
              ></div>
            </div>

            <!-- 工序卡片 -->
            <button
              class="srp-op"
              :class="{ 'srp-op--active': isOpActive(operation) }"
              :data-merge-group-id="operationToGroupId(resolveSourceOperationId(operation)) || ''"
              @click="$emit('select-operation', resolveSourceOperationId(operation))"
            >
              <!-- 第一行：序号 + 名称 + 覆盖率 -->
              <div class="srp-op-row1">
                <span class="srp-op-seq">{{ operation.sequence }}</span>
                <div class="srp-op-names">
                  <span class="srp-op-name">{{ operationDisplayName(operation) }}</span>
                </div>
                <span class="srp-op-cov">
                  {{ formatCoverage(operation.coverage_count, operation.sample_count) }}
                </span>
              </div>

              <!-- 第二行：重复标签 -->
              <div v-if="operationDuplicateLabel(operation) || sourceOperationLabel(operation)" class="srp-op-tags">
                <span class="srp-tag-warn">{{ operationDuplicateLabel(operation) }}</span>
                <span v-if="sourceOperationLabel(operation)" class="srp-tag-neutral">{{ sourceOperationLabel(operation) }}</span>
              </div>

              <!-- 第三行：工步折叠区 -->
              <div
                v-if="hasSteps(operation)"
                class="srp-op-steps"
                @click.stop
              >
                <button
                  class="srp-steps-btn"
                  @click="toggleSteps(operation)"
                >
                  <svg
                    class="srp-steps-chevron"
                    :class="{ 'srp-steps-chevron--open': expandedIds.has(operationDisplayKey(operation)) }"
                    viewBox="0 0 16 16"
                    width="9"
                    height="9"
                    fill="none"
                  >
                    <path
                      d="M6 4l4 4-4 4"
                      stroke="currentColor"
                      stroke-width="1.8"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    />
                  </svg>
                  <span>工步</span>
                  <span class="srp-steps-count">{{ stepCount(operation) }}</span>
                </button>

                <Transition name="srp-expand">
                  <div v-if="expandedIds.has(operationDisplayKey(operation))" class="srp-chips">
                    <span
                      v-for="step in getSteps(operation)"
                      :key="step"
                      class="srp-chip"
                    >{{ step }}</span>
                    <span
                      v-for="step in getAttachedSteps(operation)"
                      :key="'a_' + step"
                      class="srp-chip srp-chip--attached"
                    >{{ step }}</span>
                  </div>
                </Transition>
              </div>
            </button>
          </div>
        </div>
      </section>
    </div>

    <div v-else class="srp-empty">当前任务还没有可展示的工艺路线全集。</div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { PropType } from 'vue'
import { formatRouteDisplayName } from '@/composables/routeNameDisplay'

const props = defineProps({
  sections: {
    type: Array as PropType<Array<Record<string, any>>>,
    default: () => [],
  },
  activeGroupId: {
    type: String,
    default: '',
  },
  activeOperationIds: {
    type: Array as PropType<number[]>,
    default: () => [],
  },
  operationToGroupId: {
    type: Function as PropType<(operationId: number) => string>,
    required: true,
  },
  operationDisplayName: {
    type: Function as PropType<(operation: Record<string, any>) => string>,
    required: true,
  },
  operationDuplicateLabel: {
    type: Function as PropType<(operation: Record<string, any>) => string>,
    required: true,
  },
  formatCoverage: {
    type: Function as PropType<(hit?: number | null, total?: number | null) => string>,
    required: true,
  },
})

defineEmits<{
  (e: 'select-operation', operationId: number): void
}>()

// ── 工步展开状态 ──
const expandedIds = ref<Set<string>>(new Set())

function operationDisplayKey(operation: Record<string, any>): string {
  const explicit = String(operation?.display_key || '').trim()
  if (explicit) return explicit
  return String(operation?.id ?? '')
}

function resolveSourceOperationId(operation: Record<string, any>): number {
  return Number(operation?.source_operation_id || operation?.id || 0)
}

function sourceOperationLabel(operation: Record<string, any>): string {
  const rawName = formatRouteDisplayName(String(operation?.source_operation_name || ''))
  const displayName = formatRouteDisplayName(String(operation?.name || ''))
  if (!rawName || rawName === displayName) return ''
  return `来源：${rawName}`
}

function toggleSteps(operation: Record<string, any>) {
  const id = operationDisplayKey(operation)
  const next = new Set(expandedIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expandedIds.value = next
}

// ── 激活状态判断 ──
function isOpActive(operation: Record<string, any>): boolean {
  const sourceId = resolveSourceOperationId(operation)
  return (
    (!!props.activeGroupId && props.operationToGroupId(sourceId) === props.activeGroupId) ||
    props.activeOperationIds.includes(sourceId)
  )
}

// ── 工步相关 ──
function getSteps(operation: Record<string, any>): string[] {
  return Array.isArray(operation?.step_items) ? operation.step_items.filter(Boolean) : []
}

function getAttachedSteps(operation: Record<string, any>): string[] {
  return Array.isArray(operation?.attached_step_items) ? operation.attached_step_items.filter(Boolean) : []
}

function hasSteps(operation: Record<string, any>): boolean {
  return getSteps(operation).length > 0 || getAttachedSteps(operation).length > 0
}

function stepCount(operation: Record<string, any>): number {
  return getSteps(operation).length + getAttachedSteps(operation).length
}

</script>

<style scoped>
/* ══════════════════════════════════════
   根容器
══════════════════════════════════════ */
.srp-root {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

/* ══════════════════════════════════════
   面板头部
══════════════════════════════════════ */
.srp-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 18px 20px 14px;
  border-bottom: 1px solid #f1f5f9;
  background: linear-gradient(135deg, #fafbff 0%, #f8fafc 100%);
  flex-shrink: 0;
}

.srp-head-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.srp-head-title {
  font-size: 15px;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.015em;
  line-height: 1.2;
}

.srp-head-sub {
  font-size: 13px;
  color: #94a3b8;
  white-space: nowrap;
  font-weight: 500;
  line-height: 1.2;
}

/* ══════════════════════════════════════
   滚动容器
══════════════════════════════════════ */
.srp-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 14px 14px 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* ══════════════════════════════════════
   段组（Section）
══════════════════════════════════════ */
.srp-section {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.srp-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 5px 8px 5px 10px;
  margin-bottom: 10px;
  background: linear-gradient(90deg, rgba(99, 102, 241, 0.07) 0%, transparent 100%);
  border-left: 3px solid #6366f1;
  border-radius: 0 6px 6px 0;
}

.srp-section-info {
  display: flex;
  align-items: baseline;
  gap: 6px;
}

.srp-section-kicker {
  font-size: 10px;
  font-weight: 700;
  color: #6366f1;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.srp-section-name {
  font-size: 13px;
  font-weight: 700;
  color: #1e293b;
}

/* ══════════════════════════════════════
   时间轴布局
══════════════════════════════════════ */
.srp-timeline {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.srp-item-wrap {
  display: flex;
  align-items: stretch;
  gap: 10px;
}

/* 轨道（圆点 + 竖线） */
.srp-track {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex-shrink: 0;
  width: 14px;
  padding-top: 12px;
}

.srp-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #cbd5e1;
  border: 2px solid #ffffff;
  box-shadow: 0 0 0 1px #cbd5e1;
  flex-shrink: 0;
  transition: all 0.15s ease;
  z-index: 1;
}

.srp-dot--active {
  background: #6366f1;
  box-shadow: 0 0 0 1px #6366f1, 0 0 0 3px rgba(99, 102, 241, 0.2);
}

.srp-line {
  flex: 1;
  width: 2px;
  background: linear-gradient(to bottom, #e2e8f0 0%, #f1f5f9 100%);
  margin: 3px 0 0;
  min-height: 8px;
}

/* ══════════════════════════════════════
   工序卡片
══════════════════════════════════════ */
.srp-op {
  flex: 1;
  min-width: 0;
  text-align: left;
  border: 1px solid transparent;
  border-radius: 8px;
  padding: 8px 10px;
  margin-bottom: 4px;
  background: #ffffff;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
  position: relative;
}

.srp-op:hover {
  background: #f8fafc;
  border-color: #e2e8f0;
}

.srp-op--active {
  background: #eef2ff;
  border-color: #c7d2fe;
  box-shadow: 0 2px 8px rgba(99, 102, 241, 0.1);
}

.srp-op--active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 5px;
  bottom: 5px;
  width: 3px;
  background: #6366f1;
  border-radius: 0 2px 2px 0;
}

/* 第一行：序号 + 名称 + 覆盖率 */
.srp-op-row1 {
  display: flex;
  align-items: center;
  gap: 7px;
}

.srp-op-seq {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 26px;
  height: 20px;
  border-radius: 5px;
  background: #f1f5f9;
  color: #475569;
  font-size: 11px;
  font-weight: 700;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  transition: background 0.15s, color 0.15s;
}

.srp-op--active .srp-op-seq {
  background: #6366f1;
  color: #ffffff;
}

.srp-op-names {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.srp-op-name {
  font-size: 13px;
  font-weight: 600;
  color: #1e293b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.4;
}

.srp-op-cov {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 600;
  color: #d97706;
  background: rgba(245, 158, 11, 0.1);
  padding: 2px 6px;
  border-radius: 5px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

/* 第二行：重复标签 */
.srp-op-tags {
  margin-top: 5px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.srp-tag-warn {
  font-size: 10px;
  font-weight: 600;
  color: #c2410c;
  background: rgba(234, 88, 12, 0.09);
  padding: 2px 7px;
  border-radius: 4px;
}

.srp-tag-neutral {
  font-size: 10px;
  font-weight: 600;
  color: #475569;
  background: #f1f5f9;
  padding: 2px 7px;
  border-radius: 4px;
}

/* ══════════════════════════════════════
   工步折叠区
══════════════════════════════════════ */
.srp-op-steps {
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px dashed #e2e8f0;
}

.srp-steps-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  font-weight: 600;
  color: #64748b;
  background: transparent;
  border: none;
  padding: 0;
  cursor: pointer;
  transition: color 0.15s;
}

.srp-steps-btn:hover {
  color: #6366f1;
}

.srp-steps-chevron {
  color: currentColor;
  transition: transform 0.2s ease;
  flex-shrink: 0;
}

.srp-steps-chevron--open {
  transform: rotate(90deg);
}

.srp-steps-count {
  background: #e2e8f0;
  color: #64748b;
  border-radius: 999px;
  padding: 1px 6px;
  font-size: 10px;
  font-weight: 700;
  transition: background 0.15s;
}

.srp-steps-btn:hover .srp-steps-count {
  background: rgba(99, 102, 241, 0.12);
  color: #6366f1;
}

/* 工步 chip 列表 */
.srp-chips {
  margin-top: 7px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.srp-chip {
  display: inline-block;
  font-size: 11px;
  color: #475569;
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  border-radius: 4px;
  padding: 2px 6px;
  line-height: 1.4;
}

.srp-chip--attached {
  color: #64748b;
  background: #f8fafc;
  border-style: dashed;
}

/* 展开动画 */
.srp-expand-enter-active,
.srp-expand-leave-active {
  transition: opacity 0.2s ease, max-height 0.25s ease;
  overflow: hidden;
  max-height: 300px;
}

.srp-expand-enter-from,
.srp-expand-leave-to {
  opacity: 0;
  max-height: 0;
}

/* ══════════════════════════════════════
   空态
══════════════════════════════════════ */
.srp-empty {
  text-align: center;
  padding: 28px 20px;
  color: #94a3b8;
  font-size: 13px;
}
</style>
