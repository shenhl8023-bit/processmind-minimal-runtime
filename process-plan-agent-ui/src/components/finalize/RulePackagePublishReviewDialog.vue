<template>
  <Teleport to="body">
    <div v-if="modelValue" class="export-review-backdrop" @click.self="cancel">
      <section class="export-review" role="dialog" aria-modal="true" aria-labelledby="publish-review-title">
        <header class="export-review__header">
          <div>
            <h2 id="publish-review-title">审核并发布规则包</h2>
            <p>请确认本次规则包的审核结果。确认后将发布规则包，下载可在发布完成后单独进行。</p>
          </div>
          <button
            type="button"
            class="export-review__close"
            aria-label="关闭审核弹窗"
            title="关闭"
            @click="cancel"
          >
            &times;
          </button>
        </header>

        <div v-if="review" class="export-review__body">
          <dl class="export-review__summary" aria-label="规则包摘要">
            <div>
              <dt>项目</dt>
              <dd>{{ review.projectName }}</dd>
            </div>
            <div>
              <dt>工序</dt>
              <dd>{{ review.processCount }} 道</dd>
            </div>
            <div>
              <dt>规则</dt>
              <dd>{{ review.ruleCount }} 条</dd>
            </div>
            <div>
              <dt>规则校验</dt>
              <dd :class="review.validation?.valid ? 'is-success' : review.validation ? 'is-danger' : 'is-warning'">
                {{ review.validation ? (review.validation.valid ? '通过' : '未通过') : '未执行' }}
              </dd>
            </div>
            <div>
              <dt>KmAI 兼容性</dt>
              <dd :class="review.status === 'ready' ? 'is-success' : 'is-danger'">
                {{ review.kmaiCompatibility ? (review.kmaiCompatibility.valid ? '兼容' : '未通过') : '未检查' }}
              </dd>
            </div>
          </dl>

          <section v-if="review.status === 'ready'" class="export-review__result is-success" aria-live="polite">
            <strong>审核通过</strong>
            <span>规则结构和 KmAI 兼容性检查均已通过，可以发布。</span>
          </section>

          <section
            v-if="review.status === 'ready' && review.manualFactors.length"
            class="export-review__manual"
          >
            <strong>运行时手工因子</strong>
            <p>
              以下手工布尔因子需要通过 <code>manual.factor_overrides</code> 提供
              <code>true/false</code>。这不会阻止发布。
            </p>
            <ul>
              <li v-for="factor in review.manualFactors" :key="factor.key">
                <code>{{ factor.key }}</code>：{{ factor.name }}
              </li>
            </ul>
          </section>

          <section v-if="review.status === 'blocked'" class="export-review__result is-danger" aria-live="polite">
            <strong>审核未通过</strong>
            <span>请返回第四步处理以下问题后重新审核。</span>
          </section>

          <div v-if="review.status === 'blocked'" class="export-review__blockers">
            <article
              v-for="detail in review.details"
              :key="`${detail.code}:${detail.sourceSegmentId}:${detail.message}`"
              class="export-review__blocker"
            >
              <dl>
                <div>
                  <dt>工序</dt>
                  <dd>{{ detail.processName || '规则包发布' }}</dd>
                </div>
                <div>
                  <dt>来源</dt>
                  <dd>{{ detail.sourceText || '未提供来源文本' }}</dd>
                </div>
                <div>
                  <dt>问题</dt>
                  <dd>{{ detail.message }}</dd>
                </div>
              </dl>
              <button
                type="button"
                class="blocker-locate"
                @click="locate(detail.sourceSegmentId)"
              >
                返回第四步处理
              </button>
            </article>
          </div>
        </div>

        <footer class="export-review__footer">
          <button type="button" @click="cancel">取消</button>
          <button
            type="button"
            class="is-primary"
            :disabled="review?.status !== 'ready'"
            @click="confirm"
          >
            确认发布
          </button>
        </footer>
      </section>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import type { RulePackagePublishReview } from '@/composables/useFinalizeRulePackagePublish'

const props = defineProps<{
  modelValue: boolean
  review: RulePackagePublishReview | null
}>()

const emit = defineEmits<{
  (event: 'update:modelValue', value: boolean): void
  (event: 'confirmed'): void
  (event: 'cancelled'): void
  (event: 'locate', sourceSegmentId: string): void
}>()

function confirm() {
  if (props.review?.status !== 'ready') return
  emit('confirmed')
  emit('update:modelValue', false)
}

function cancel() {
  emit('cancelled')
  emit('update:modelValue', false)
}

function locate(sourceSegmentId: string) {
  emit('locate', sourceSegmentId)
}
</script>

<style scoped>
.export-review-backdrop {
  position: fixed;
  z-index: 3000;
  inset: 0;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(15, 23, 42, .52);
}

.export-review {
  display: flex;
  width: min(820px, 100%);
  max-height: calc(100vh - 48px);
  flex-direction: column;
  overflow: hidden;
  border: 1px solid #dbe3ee;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 24px 64px rgba(15, 23, 42, .24);
  color: #334155;
}

.export-review__header,
.export-review__footer {
  display: flex;
  align-items: center;
}

.export-review__header {
  justify-content: space-between;
  gap: 16px;
  padding: 18px 22px;
  border-bottom: 1px solid #e2e8f0;
}

.export-review__header h2 { margin: 0; color: #0f172a; font-size: 18px; }
.export-review__header p { margin: 5px 0 0; color: #64748b; font-size: 13px; }
.export-review__close { width: 32px; height: 32px; border: 0; background: transparent; color: #64748b; cursor: pointer; font-size: 24px; line-height: 1; }
.export-review__body { display: grid; gap: 16px; min-height: 0; overflow: auto; padding: 18px 22px; background: #f8fafc; }

.export-review__summary {
  display: grid;
  grid-template-columns: minmax(150px, 1.5fr) repeat(4, minmax(100px, 1fr));
  gap: 1px;
  margin: 0;
  overflow: hidden;
  border: 1px solid #dbe3ee;
  border-radius: 7px;
  background: #dbe3ee;
}

.export-review__summary div { min-width: 0; padding: 10px 12px; background: #fff; }
.export-review__summary dt { color: #64748b; font-size: 11px; }
.export-review__summary dd { margin: 4px 0 0; overflow-wrap: anywhere; color: #0f172a; font-size: 13px; font-weight: 700; }
.export-review__summary .is-success { color: #15803d; }
.export-review__summary .is-warning { color: #b45309; }
.export-review__summary .is-danger { color: #b91c1c; }

.export-review__result,
.export-review__manual {
  display: grid;
  gap: 5px;
  padding: 12px 14px;
  border-left: 3px solid;
  background: #fff;
  font-size: 13px;
}

.export-review__result strong,
.export-review__manual strong { color: #0f172a; font-size: 14px; }
.export-review__result span { color: #64748b; }
.export-review__result.is-success { border-color: #22c55e; }
.export-review__result.is-danger { border-color: #ef4444; }
.export-review__manual { border-color: #0f766e; }
.export-review__manual p,
.export-review__manual ul { margin: 0; }
.export-review__manual ul { padding-left: 18px; }

.export-review__blockers { display: grid; gap: 10px; }
.export-review__blocker { display: grid; gap: 10px; padding: 14px; border: 1px solid #fecaca; border-radius: 7px; background: #fff; }
.export-review__blocker dl { display: grid; gap: 8px; margin: 0; }
.export-review__blocker dl div { display: grid; grid-template-columns: 54px minmax(0, 1fr); gap: 8px; }
.export-review__blocker dt { color: #64748b; font-size: 12px; font-weight: 700; }
.export-review__blocker dd { margin: 0; overflow-wrap: anywhere; color: #334155; font-size: 13px; }
.blocker-locate { justify-self: start; border: 0; padding: 0; background: transparent; color: #4f46e5; cursor: pointer; font-weight: 700; }

.export-review__footer { justify-content: flex-end; gap: 8px; padding: 14px 22px; border-top: 1px solid #e2e8f0; }
.export-review__footer button { min-width: 88px; padding: 8px 13px; border: 1px solid #cbd5e1; border-radius: 6px; background: #fff; color: #334155; cursor: pointer; }
.export-review__footer button.is-primary { border-color: #4f46e5; background: #4f46e5; color: #fff; }
.export-review__footer button:disabled { opacity: .5; cursor: not-allowed; }

@media (max-width: 760px) {
  .export-review-backdrop { padding: 10px; }
  .export-review { max-height: calc(100vh - 20px); }
  .export-review__summary { grid-template-columns: 1fr 1fr; }
  .export-review__summary div:first-child { grid-column: 1 / -1; }
}
</style>
