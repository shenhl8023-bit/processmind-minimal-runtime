<template>
  <div class="precheck-overlay" @click.self="$emit('close')">
    <section class="precheck-dialog" role="dialog" aria-modal="true" aria-labelledby="precheck-title">
      <header class="precheck-header">
        <span class="precheck-status-mark" :class="{ 'precheck-status-mark--blocked': !result.ok }" aria-hidden="true">
          {{ result.ok ? '✓' : '!' }}
        </span>
        <div class="precheck-heading">
          <span class="precheck-kicker">发布预检</span>
          <h2 id="precheck-title">{{ result.ok ? '规则包可以发布' : '规则包暂不可发布' }}</h2>
        </div>
        <button class="precheck-close" type="button" aria-label="关闭预检结果" @click="$emit('close')">×</button>
      </header>

      <div class="precheck-body">
        <p v-if="result.ok" class="precheck-summary precheck-summary--ready">
          全量校验已通过，规则包已满足发布条件。
        </p>
        <template v-else>
          <p class="precheck-summary precheck-summary--blocked">
            还有 {{ result.blockers.length || 1 }} 项需要修复
          </p>
          <ul v-if="result.blockers.length" class="precheck-blocker-list">
            <li v-for="(blocker, index) in result.blockers" :key="`${blocker.code}-${blocker.process_id || index}`" class="precheck-blocker">
              <div class="precheck-blocker-copy">
                <strong v-if="blocker.process_name">{{ blocker.process_name }}</strong>
                <p v-if="dependencyLabels(blocker).length" class="precheck-dependency-context">
                  前置工序：{{ dependencyLabels(blocker).join('、') }}
                </p>
                <p>{{ blockerLabel(blocker) }}</p>
              </div>
              <button class="precheck-repair-button" type="button" @click="openRepair(blocker)">
                {{ repairLabel(blocker) }}
              </button>
            </li>
          </ul>
          <p v-else class="precheck-empty-blocker">预检未通过，请回到规则审核检查相关内容。</p>
        </template>

        <section v-if="result.export_summary" class="precheck-export-summary">
          <strong>本次交付 {{ result.export_summary.exported_process_count }} 道工序、{{ result.export_summary.exported_step_count }} 个工步</strong>
          <p>未映射的加工工步不参与交付，辅助工序按规则保留。</p>
          <details v-if="result.export_summary.excluded_processes.length || result.export_summary.excluded_steps.length">
            <summary>查看未参与交付的工序和工步</summary>
            <ul>
              <li v-for="process in result.export_summary.excluded_processes" :key="process.process_id">
                {{ process.process_name }}：{{ process.reason }}
              </li>
              <li v-for="step in result.export_summary.excluded_steps" :key="step.step_id">
                {{ step.process_name }} / {{ step.step_name }}：{{ step.reason }}
              </li>
            </ul>
          </details>
        </section>

        <details v-if="passedChecks.length" class="precheck-passed-checks">
          <summary>查看已通过检查（{{ passedChecks.length }}）</summary>
          <ul>
            <li v-for="item in passedChecks" :key="item.code">
              <span class="passed-check-icon" aria-hidden="true">✓</span>
              <div>
                <strong>{{ item.label }}</strong>
                <p>{{ item.message }}</p>
              </div>
            </li>
          </ul>
        </details>
      </div>

      <footer class="precheck-footer">
        <button class="precheck-done-button" type="button" @click="$emit('close')">知道了</button>
      </footer>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { RulePackagePrecheckResult } from '@/api/extract'

const props = defineProps<{ result: RulePackagePrecheckResult }>()

const emit = defineEmits<{
  close: []
  'open-template-mapping': []
  'open-rule-review': [blocker: Record<string, any>]
}>()

const passedChecks = computed(() => props.result.checklist.filter(item => item.status === 'passed'))

function blockerLabel(blocker: Record<string, any>) {
  const message = String(blocker.message || '').trim()
  if (String(blocker.process_name || '').trim()) return message || '请检查这道工序的规则设置。'
  const parts: string[] = []
  if (message) parts.push(message)
  const requiredBy = Array.isArray(blocker.required_by_labels)
    ? blocker.required_by_labels.map((label: unknown) => String(label).trim()).filter(Boolean)
    : []
  if (requiredBy.length) parts.push(`关联：${requiredBy.join('、')}`)
  return parts.join(' · ') || '存在未解决的发布预检问题。'
}

function dependencyLabels(blocker: Record<string, any>) {
  const names = Array.isArray(blocker.prerequisite_process_names)
    ? blocker.prerequisite_process_names.map((name: unknown) => String(name).trim()).filter(Boolean)
    : []
  return names.length ? names : Array.isArray(blocker.required_by_labels)
    ? blocker.required_by_labels.map((name: unknown) => String(name).trim()).filter(Boolean)
    : []
}

function isTemplateMappingBlocker(blocker: Record<string, any>) {
  const code = String(blocker.code || '').toLowerCase()
  const message = String(blocker.message || '')
  return ['group_template_missing', 'group_template_mapping_missing'].includes(code)
    || /template|mapping|group/i.test(code)
    || /模板映射|分组模板|模板分组|映射页/.test(message)
}

function repairLabel(blocker: Record<string, any>) {
  if (isTemplateMappingBlocker(blocker)) return '修复映射'
  if (String(blocker.code || '').includes('unconfirmed')) return '查看待处理规则'
  const processName = String(blocker.process_name || '').trim()
  if (processName) return `定位“${processName}”`
  return '返回规则审核'
}

function openRepair(blocker: Record<string, any>) {
  if (isTemplateMappingBlocker(blocker)) emit('open-template-mapping')
  else emit('open-rule-review', blocker)
}
</script>

<style scoped>
.precheck-overlay {
  position: fixed;
  inset: 0;
  z-index: 70;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(15, 23, 42, .45);
  backdrop-filter: blur(2px);
}

.precheck-dialog {
  width: min(520px, 100%);
  max-height: min(680px, calc(100vh - 48px));
  overflow: auto;
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  background: #ffffff;
  box-shadow: 0 24px 64px rgba(15, 23, 42, .2);
}

.precheck-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 20px 22px 16px;
  border-bottom: 1px solid #f1f5f9;
}

.precheck-status-mark {
  display: grid;
  width: 34px;
  height: 34px;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 50%;
  background: #dcfce7;
  color: #15803d;
  font-size: 18px;
  font-weight: 800;
}

.precheck-status-mark--blocked {
  background: #ffedd5;
  color: #c2410c;
}

.precheck-heading { min-width: 0; flex: 1; }
.precheck-kicker { color: #64748b; font-size: 11px; font-weight: 700; letter-spacing: .04em; }
.precheck-heading h2 { margin: 3px 0 0; color: #0f172a; font-size: 17px; line-height: 1.35; }

.precheck-close {
  display: grid;
  width: 32px;
  height: 32px;
  flex: 0 0 auto;
  place-items: center;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: #64748b;
  font-size: 22px;
  cursor: pointer;
}

.precheck-close:hover { background: #f1f5f9; color: #0f172a; }
.precheck-close:focus-visible, .precheck-repair-button:focus-visible, .precheck-done-button:focus-visible { outline: 2px solid #818cf8; outline-offset: 2px; }

.precheck-body { padding: 18px 22px 8px; }
.precheck-export-summary { margin-top: 14px; padding: 12px; border-radius: 8px; background: #f1f5f9; color: #334155; font-size: 13px; }
.precheck-export-summary p { margin: 6px 0; }
.precheck-export-summary summary { cursor: pointer; }
.precheck-export-summary ul { padding-left: 20px; line-height: 1.7; }
.precheck-summary { margin: 0 0 12px; font-size: 13px; line-height: 1.55; }
.precheck-summary--ready { color: #166534; }
.precheck-summary--blocked { color: #9a3412; font-weight: 700; }

.precheck-blocker-list { display: grid; gap: 8px; margin: 0; padding: 0; list-style: none; }
.precheck-blocker {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 11px 12px;
  border: 1px solid #fed7aa;
  border-radius: 9px;
  background: #fffaf5;
}

.precheck-blocker-copy { display: grid; min-width: 0; flex: 1; gap: 3px; }
.precheck-blocker-copy > strong { color: #7c2d12; font-size: 12.5px; line-height: 1.4; }
.precheck-blocker-copy p { min-width: 0; margin: 0; color: #7c2d12; font-size: 12.5px; line-height: 1.5; overflow-wrap: anywhere; }
.precheck-blocker-copy .precheck-dependency-context { color: #9a3412; font-weight: 650; }
.precheck-repair-button { flex: 0 0 auto; padding: 6px 9px; border: 1px solid #fdba74; border-radius: 7px; background: #ffffff; color: #9a3412; font-size: 11.5px; font-weight: 650; cursor: pointer; }
.precheck-repair-button:hover { background: #fff1e6; }
.precheck-empty-blocker { margin: 0; color: #64748b; font-size: 12.5px; }

.precheck-passed-checks { margin-top: 14px; border-top: 1px solid #e2e8f0; color: #475569; }
.precheck-passed-checks summary { padding: 12px 0; color: #475569; font-size: 12px; font-weight: 600; cursor: pointer; }
.precheck-passed-checks ul { display: grid; gap: 8px; margin: 0 0 8px; padding: 0; list-style: none; }
.precheck-passed-checks li { display: flex; align-items: flex-start; gap: 9px; padding: 9px 10px; border-radius: 8px; background: #f8fafc; }
.passed-check-icon { color: #15803d; font-size: 13px; font-weight: 800; }
.precheck-passed-checks strong { color: #334155; font-size: 12px; }
.precheck-passed-checks p { margin: 2px 0 0; color: #64748b; font-size: 11.5px; line-height: 1.45; }

.precheck-footer { display: flex; justify-content: flex-end; padding: 12px 22px 18px; }
.precheck-done-button { min-height: 34px; padding: 6px 14px; border: 1px solid #4f46e5; border-radius: 8px; background: #4f46e5; color: #ffffff; font-size: 12px; font-weight: 700; cursor: pointer; }
.precheck-done-button:hover { background: #4338ca; }

@media (max-width: 520px) {
  .precheck-overlay { padding: 12px; }
  .precheck-header { padding: 16px; }
  .precheck-body { padding: 16px 16px 8px; }
  .precheck-footer { padding: 10px 16px 16px; }
  .precheck-blocker { align-items: flex-start; flex-direction: column; }
}
</style>
