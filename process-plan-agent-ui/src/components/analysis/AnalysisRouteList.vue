<template>
  <section class="analysis-column analysis-column-left">
    <div class="panel-head">
      <div class="panel-title">已保存路线 <span class="panel-badge-inline">只读</span></div>
    </div>

    <div class="route-list">
      <div
        v-for="(segment, idx) in segments"
        :key="segment.id"
        class="route-item-wrap"
      >
        <div class="route-track">
          <div class="route-dot" :class="{ 'route-dot--active': segment.id === selectedSegmentId }"></div>
          <div v-if="idx < segments.length - 1" class="route-line"></div>
        </div>

        <button
          type="button"
          class="route-item"
          :class="{ active: segment.id === selectedSegmentId }"
          @click="emit('select', String(segment.id))"
        >
          <div class="route-header-row">
            <div class="route-title-group">
              <span class="route-seq">{{ segment.sequence }}</span>
              <span class="route-name">{{ segmentDisplayName(segment) }}</span>
            </div>
            <span class="route-state-badge" :class="segmentProgressClass(segment)">
              {{ segmentProgressLabel(segment) }}
            </span>
          </div>

          <div class="route-main">
            <div class="route-meta-row">
              <span class="route-meta-coverage">样本 {{ segmentCoverageLabel(segment) }}</span>
              <span v-if="segment.step_family" class="route-meta-tag">{{ segment.step_family }}</span>
              <span v-if="segmentPhaseLabel(segment)" class="route-meta-tag">{{ segmentPhaseLabel(segment) }}</span>
              <span class="route-meta-details">{{ segment.detail_coverage.matched_rows }} 条明细</span>
            </div>

            <div
              v-if="segmentStepCount(segment) > 0"
              class="route-steps"
              @click.stop
            >
              <span
                class="route-steps-btn"
                role="button"
                tabindex="0"
                @click.stop="toggleSegmentSteps(segment.id)"
                @keydown.enter.prevent="toggleSegmentSteps(segment.id)"
                @keydown.space.prevent="toggleSegmentSteps(segment.id)"
              >
                <svg
                  class="route-steps-chevron"
                  :class="{ 'route-steps-chevron--open': isSegmentStepsExpanded(segment.id) }"
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
                <span class="route-steps-count">{{ segmentStepCount(segment) }}</span>
              </span>

              <Transition name="route-steps-expand">
                <div v-if="isSegmentStepsExpanded(segment.id)" class="route-step-chips">
                  <span
                    v-for="step in segmentPrimarySteps(segment)"
                    :key="`${segment.id}-step-${step}`"
                    class="route-step-chip"
                  >{{ step }}</span>
                  <span
                    v-for="step in segmentAttachedSteps(segment)"
                    :key="`${segment.id}-attached-${step}`"
                    class="route-step-chip route-step-chip-attached"
                  >{{ step }}</span>
                </div>
              </Transition>
            </div>
          </div>
        </button>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
defineProps<{
  segments: any[]
  selectedSegmentId: string
  segmentDisplayName: (segment: any) => string
  segmentProgressClass: (segment: any) => string
  segmentProgressLabel: (segment: any) => string
  segmentCoverageLabel: (segment: any) => string
  segmentPhaseLabel: (segment: any) => string
  segmentStepCount: (segment: any) => number
  isSegmentStepsExpanded: (segmentId: string) => boolean
  toggleSegmentSteps: (segmentId: string) => void
  segmentPrimarySteps: (segment: any) => string[]
  segmentAttachedSteps: (segment: any) => string[]
}>()

const emit = defineEmits<{
  (event: 'select', segmentId: string): void
}>()
</script>

<style scoped>
.analysis-column {
  min-width: 0;
  overflow-y: auto;
}

.analysis-column-left {
  border-radius: 14px;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
  padding: 14px;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
  margin-bottom: 10px;
}

.panel-title {
  font-size: 15px;
  font-weight: 700;
  color: #0f172a;
  display: flex;
  align-items: center;
  gap: 8px;
}

.panel-badge-inline {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
  background: #f1f5f9;
  color: #64748b;
}

.route-list {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.route-item-wrap {
  display: flex;
  gap: 10px;
  position: relative;
}

.route-track {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex-shrink: 0;
  width: 14px;
  padding-top: 14px;
}

.route-dot {
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

.route-dot--active {
  background: #6366f1;
  box-shadow: 0 0 0 1px #6366f1, 0 0 0 3px rgba(99, 102, 241, 0.25);
}

.route-line {
  flex: 1;
  width: 2px;
  min-height: 16px;
  background: linear-gradient(to bottom, #e2e8f0 0%, #f1f5f9 100%);
  margin: 4px 0 -4px;
}

.route-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding: 8px 10px;
  border-radius: 6px;
  border: 1px solid #f1f5f9;
  background: #ffffff;
  cursor: pointer;
  text-align: left;
  position: relative;
  margin-bottom: 4px;
  transition: all 0.15s ease;
}

.route-item:hover {
  background: #f8fafc;
  border-color: #cbd5e1;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
}

.route-item.active {
  background: #fafcff;
  border-color: #cbd5e1;
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.03);
}

.route-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  width: 100%;
}

.route-title-group {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.route-seq {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 22px;
  height: 16px;
  padding: 0 5px;
  border-radius: 3px;
  background: #f1f5f9;
  color: #475569;
  font-weight: 700;
  font-size: 10px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  flex-shrink: 0;
  border: 1px solid #e2e8f0;
  transition: all 0.15s ease;
}

.route-item.active .route-seq {
  background: #6366f1;
  color: #ffffff;
  border-color: #6366f1;
}

.route-name {
  font-size: 13px;
  font-weight: 600;
  color: #0f172a;
}

.route-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.route-meta-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
  margin-top: 4px;
  flex-wrap: wrap;
  font-size: 11px;
  color: #94a3b8;
}

.route-meta-tag {
  font-size: 10px;
  font-weight: 600;
  color: #64748b;
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  padding: 1px 5px;
  border-radius: 3px;
}

.route-meta-details {
  font-size: 11.5px;
  color: #94a3b8;
  margin-left: auto;
}

.route-meta-coverage {
  color: #4f46e5;
  font-weight: 700;
}

.route-steps {
  margin-top: 4px;
  padding-top: 6px;
  border-top: 1px solid #f1f5f9;
}

.route-steps-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0;
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: 11px;
  font-weight: 600;
  color: #64748b;
  transition: color 0.12s ease;
}

.route-steps-btn:hover {
  color: #6366f1;
}

.route-steps-chevron {
  color: currentColor;
  flex-shrink: 0;
  transition: transform 0.2s ease;
}

.route-steps-chevron--open {
  transform: rotate(90deg);
}

.route-steps-count {
  background: #f1f5f9;
  color: #475569;
  border-radius: 4px;
  padding: 1px 5px;
  font-size: 10px;
  font-family: ui-monospace, monospace;
  font-weight: 700;
  border: 1px solid #e2e8f0;
  transition: all 0.12s;
}

.route-steps-btn:hover .route-steps-count {
  background: rgba(99, 102, 241, 0.08);
  border-color: rgba(99, 102, 241, 0.15);
  color: #6366f1;
}

.route-step-chips {
  margin-top: 7px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.route-step-chip {
  display: inline-block;
  font-size: 11px;
  color: #475569;
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  border-radius: 4px;
  padding: 2px 6px;
  line-height: 1.4;
}

.route-step-chip-attached {
  color: #64748b;
  background: #f8fafc;
  border-style: dashed;
}

.route-steps-expand-enter-active,
.route-steps-expand-leave-active {
  transition: opacity 0.2s ease, max-height 0.25s ease;
  overflow: hidden;
  max-height: 300px;
}

.route-steps-expand-enter-from,
.route-steps-expand-leave-to {
  opacity: 0;
  max-height: 0;
}

.route-state-badge {
  display: inline-flex;
  align-items: center;
  align-self: flex-start;
  flex-shrink: 0;
  border-radius: 999px;
  padding: 1px 6px;
  font-size: 10px;
  line-height: 1.2;
  font-weight: 600;
  background: #e2e8f0;
  color: #475569;
}

.route-state-badge.is-completed {
  background: rgba(34, 197, 94, 0.14);
  color: #15803d;
}

.route-state-badge.is-started {
  background: rgba(99, 102, 241, 0.12);
  color: #4338ca;
}

.route-state-badge.is-pending {
  background: rgba(245, 158, 11, 0.08);
  color: #d97706;
}
</style>
