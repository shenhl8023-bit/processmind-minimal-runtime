<template>
  <aside class="route-nav card">
    <div class="route-nav-head">
      <div class="section-title">{{ title }}</div>
    </div>

    <div class="phase-list">
      <div
        v-for="(item, idx) in items"
        :key="item.segment.id"
        class="phase-item-wrap"
      >
        <div class="phase-track">
          <div class="phase-dot" :class="{ 'phase-dot--active': activeSegmentId === item.segment.id }"></div>
          <div v-if="idx < items.length - 1" class="phase-line"></div>
        </div>

        <button
          type="button"
          class="phase-item"
          :class="{ active: activeSegmentId === item.segment.id }"
          @click="$emit('focus', item.segment.id)"
        >
          <div class="phase-header-row">
            <div class="phase-title-group">
              <span class="phase-item-seq">{{ item.segment.sequence }}</span>
              <span class="phase-item-name">{{ displayName(item.segment) }}</span>
            </div>
            <span v-if="item.edited" class="phase-item-edited">已改</span>
          </div>

          <div v-if="metaLabel(item.segment)" class="phase-meta-row">
            <span class="phase-item-meta">{{ metaLabel(item.segment) }}</span>
          </div>

          <div
            v-if="stepCount(item.segment) > 0"
            class="phase-steps-row"
            @click.stop
          >
            <span
              class="phase-steps-btn"
              role="button"
              tabindex="0"
              @click.stop="$emit('toggle-steps', item.segment.id)"
              @keydown.enter.prevent="$emit('toggle-steps', item.segment.id)"
              @keydown.space.prevent="$emit('toggle-steps', item.segment.id)"
            >
              <svg
                class="phase-steps-chevron"
                :class="{ 'phase-steps-chevron--open': isStepsExpanded(item.segment.id) }"
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
              <span class="phase-steps-count">{{ stepCount(item.segment) }}</span>
            </span>
            <Transition name="phase-item-steps-expand">
              <div
                v-if="isStepsExpanded(item.segment.id)"
                class="phase-item-step-chips"
              >
                <span
                  v-for="step in primarySteps(item.segment)"
                  :key="`${item.segment.id}-step-${step}`"
                  class="phase-item-step-chip"
                >{{ step }}</span>
                <span
                  v-for="step in attachedSteps(item.segment)"
                  :key="`${item.segment.id}-attached-${step}`"
                  class="phase-item-step-chip phase-item-step-chip-attached"
                >{{ step }}</span>
              </div>
            </Transition>
          </div>
        </button>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import type { SavedNormalizedRouteVersionResult } from '@/api'
import type { FinalizeCard } from '@/composables/finalizeViewHelpers'

type Segment = SavedNormalizedRouteVersionResult['segments'][number]

defineProps<{
  title: string
  items: FinalizeCard[]
  activeSegmentId: string
  displayName: (segment: Segment) => string
  metaLabel: (segment: Segment) => string
  stepCount: (segment: any) => number
  primarySteps: (segment: any) => string[]
  attachedSteps: (segment: any) => string[]
  isStepsExpanded: (segmentId: string) => boolean
}>()

defineEmits<{
  focus: [segmentId: string]
  'toggle-steps': [segmentId: string]
}>()
</script>

<style scoped>
.route-nav {
  min-width: 0;
  overflow-y: auto;
  border-radius: 14px;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
  padding: 14px;
}

.route-nav-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.section-title {
  font-size: 15px;
  font-weight: 700;
  color: #0f172a;
  display: flex;
  align-items: center;
  gap: 8px;
  letter-spacing: -0.01em;
}

.phase-list {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 0;
}

.phase-item-wrap {
  display: flex;
  gap: 8px;
  position: relative;
}

.phase-track {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex-shrink: 0;
  width: 14px;
  padding-top: 13px;
}

.phase-dot {
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

.phase-dot--active {
  background: #6366f1;
  box-shadow: 0 0 0 1px #6366f1, 0 0 0 3px rgba(99, 102, 241, 0.25);
}

.phase-line {
  flex: 1;
  width: 2px;
  min-height: 12px;
  background: linear-gradient(to bottom, #e2e8f0 0%, #f1f5f9 100%);
  margin: 3px 0 -3px;
}

.phase-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 7px 10px;
  border-radius: 6px;
  border: 1px solid #f1f5f9;
  background: #ffffff;
  cursor: pointer;
  text-align: left;
  position: relative;
  margin-bottom: 4px;
  transition: all 0.15s ease;
}

.phase-item:hover {
  background: #f8fafc;
  border-color: #cbd5e1;
  box-shadow: 0 2px 6px rgba(15, 23, 42, 0.04);
}

.phase-item.active {
  background: #fafcff;
  border-color: #c7d2fe;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.03);
}

.phase-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
}

.phase-title-group {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
}

.phase-item-seq {
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

.phase-item.active .phase-item-seq {
  background: #6366f1;
  color: #ffffff;
  border-color: #6366f1;
}

.phase-item-name {
  font-size: 13px;
  font-weight: 600;
  color: #0f172a;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}

.phase-meta-row {
  padding-left: 0;
}

.phase-item-meta {
  font-size: 11px;
  color: #94a3b8;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: block;
}

.phase-item-edited {
  font-size: 10px;
  font-weight: 600;
  color: #b45309;
  background: #fef3c7;
  border-radius: 999px;
  padding: 1px 6px;
  flex-shrink: 0;
  white-space: nowrap;
}

.phase-steps-row {
  margin-top: 3px;
  padding-top: 5px;
  border-top: 1px solid #f1f5f9;
}

.phase-steps-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 0;
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: 11px;
  font-weight: 600;
  color: #64748b;
  transition: color 0.12s ease;
}

.phase-steps-btn:hover {
  color: #6366f1;
}

.phase-steps-chevron {
  color: currentColor;
  flex-shrink: 0;
  transition: transform 0.2s ease;
}

.phase-steps-chevron--open {
  transform: rotate(90deg);
}

.phase-steps-count {
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

.phase-steps-btn:hover .phase-steps-count {
  background: rgba(99, 102, 241, 0.08);
  border-color: rgba(99, 102, 241, 0.15);
  color: #6366f1;
}

.phase-item-step-chips {
  margin-top: 6px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.phase-item-step-chip {
  display: inline-block;
  font-size: 11px;
  color: #475569;
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  border-radius: 4px;
  padding: 2px 6px;
  line-height: 1.4;
}

.phase-item-step-chip-attached {
  color: #64748b;
  background: #f8fafc;
  border-style: dashed;
}

.phase-item-steps-expand-enter-active,
.phase-item-steps-expand-leave-active {
  transition: opacity 0.2s ease, max-height 0.25s ease;
  overflow: hidden;
  max-height: 300px;
}

.phase-item-steps-expand-enter-from,
.phase-item-steps-expand-leave-to {
  opacity: 0;
  max-height: 0;
}
</style>
