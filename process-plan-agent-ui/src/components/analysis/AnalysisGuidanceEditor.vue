<template>
  <div class="guidance-editor">
    <p>配置用于后续提问、推荐和规则生成。已保存的回答及已审核规则保留当前内容。</p>
    <label class="wide-label">项目提问及推荐说明<textarea v-model="draft.guidance" rows="3" /></label>
    <div class="guidance-columns">
      <label>方位候选（用逗号分隔）<input :value="draft.directions.join('，')" @change="draft.directions = tokens(($event.target as HTMLInputElement).value)" /></label>
      <label>项目材料牌号（用逗号分隔）<input :value="draft.materials.join('，')" @change="draft.materials = tokens(($event.target as HTMLInputElement).value)" /></label>
    </div>
    <h3>加工特征对应</h3>
    <div v-for="(features, group) in draft.feature_mappings" :key="group" class="mapping-row">
      <label>{{ group }}<input :value="features.join('，')" @change="draft.feature_mappings[group] = tokens(($event.target as HTMLInputElement).value)" /></label>
      <button type="button" @click="delete draft.feature_mappings[group]">删除</button>
    </div>
    <div class="add-row"><input v-model="newGroup" placeholder="新特征类别名称" /><button type="button" :disabled="!newGroup.trim() || Boolean(draft.feature_mappings[newGroup.trim()])" @click="addGroup">新增类别</button></div>
    <h3>逐工序推荐</h3>
    <p>同名工序从第二处起使用“工序名#2”等编号。没有可靠依据时选“不设推荐”，系统会保留提问。</p>
    <div v-for="key in operationKeys" :key="key" class="operation-guidance">
      <div class="guidance-columns">
        <strong>{{ key }}</strong>
        <label>特征类别<select v-model="entry(key).feature_group"><option value="">未指定</option><option v-for="group in Object.keys(draft.feature_mappings)" :key="group">{{ group }}</option></select></label>
        <label>推荐安排<select :value="entry(key).recommendation?.mode || ''" @change="changeMode(key, ($event.target as HTMLSelectElement).value)"><option value="">不设推荐</option><option value="mainline">主工序</option><option value="manual">Bool 人工安排</option><option value="condition">条件工序</option><option value="relation">关联工序</option></select></label>
      </div>
      <template v-if="entry(key).recommendation?.mode === 'condition'">
        <label>判断依据<select v-model="entry(key).recommendation!.basis"><option value="feature">特征与方位</option><option value="precision">尺寸精度 IT</option><option value="roughness">粗糙度 Ra</option><option value="material">材料牌号</option><option value="hardness">目标硬度</option><option value="requirement">本工序明确要求</option></select></label>
        <div v-if="entry(key).recommendation!.basis === 'feature'" class="guidance-columns">
          <label>推荐特征（逗号分隔）<input :value="entry(key).recommendation!.features?.join('，')" @change="entry(key).recommendation!.features = tokens(($event.target as HTMLInputElement).value)" /></label>
          <label>推荐方位<select v-model="entry(key).recommendation!.direction"><option value="">请选择</option><option v-for="direction in draft.directions" :key="direction">{{ direction }}</option></select></label>
        </div>
        <label v-if="entry(key).recommendation!.basis === 'material'">推荐材料（逗号分隔）<input :value="entry(key).recommendation!.materials?.join('，')" @change="entry(key).recommendation!.materials = tokens(($event.target as HTMLInputElement).value)" /></label>
        <label v-if="entry(key).recommendation!.basis === 'precision'">IT 上限（等级数字越小精度越高）<input v-model.number="entry(key).recommendation!.it_threshold" type="number" min="1" max="18" step="1" /></label>
        <label v-if="entry(key).recommendation!.basis === 'roughness' || entry(key).recommendation!.basis === 'precision'">Ra 备用阈值（μm，可选）<input v-model.number="entry(key).recommendation!.ra_threshold" type="number" min="0" step="any" /></label>
      </template>
      <label v-if="entry(key).recommendation?.mode === 'relation'">来源工序名称<input v-model="entry(key).recommendation!.source_operation_name" placeholder="例如：镀铜" /></label>
      <label>本工序说明<input v-model="entry(key).instruction" /></label>
    </div>
    <p v-if="error" role="alert" class="guidance-error">{{ error }}</p>
    <div class="guidance-footer"><button type="button" :disabled="saving" @click="emit('cancel')">取消</button><button type="button" :disabled="saving" @click="save">{{ saving ? '正在保存…' : '保存项目配置' }}</button></div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { saveAnalysisGuidance, type AnalysisGuidanceConfiguration } from '@/api/analysisGuidance'
import { createGuidanceEditorDraft } from '@/composables/analysisGuidanceEditor'
const props = defineProps<{ projectId: number; configuration: AnalysisGuidanceConfiguration; operations: string[] }>()
const emit = defineEmits<{ saved: [configuration: AnalysisGuidanceConfiguration]; cancel: [] }>()
const draft = ref<AnalysisGuidanceConfiguration>(createGuidanceEditorDraft(props.configuration, props.operations))
const newGroup = ref(''), saving = ref(false), error = ref('')
const tokens = (text: string) => text.split(/[,，、;；\n]+/).map(v => v.trim()).filter(Boolean)
const operationKeys = computed(() => [...new Set([...props.operations, ...Object.keys(draft.value.operation_guidance)])])
function entry(key: string) { return draft.value.operation_guidance[key] ||= {} }
function addGroup() { draft.value.feature_mappings[newGroup.value.trim()] = []; newGroup.value = '' }
function changeMode(key: string, mode: string) {
  if (!mode) { delete entry(key).recommendation; return }
  entry(key).recommendation = { mode: mode as any, ...(mode === 'condition' ? { basis: 'requirement' as const } : {}) }
}
async function save() {
  saving.value = true; error.value = ''
  try {
    const next = JSON.parse(JSON.stringify(draft.value)) as AnalysisGuidanceConfiguration
    Object.values(next.operation_guidance).forEach(item => {
      if (!item.feature_group) delete item.feature_group
      const r = item.recommendation
      if (!r) return
      const keep = new Set(['mode', ...(r.mode === 'condition' ? ['basis', ...(r.basis === 'feature' ? ['features', 'direction'] : r.basis === 'material' ? ['materials'] : r.basis === 'precision' ? ['it_threshold', 'ra_threshold'] : r.basis === 'roughness' ? ['ra_threshold'] : [])] : r.mode === 'relation' ? ['source_operation_name', 'source_segment_id'] : [])])
      for (const k of Object.keys(r)) if (!keep.has(k) || (r as any)[k] === '') delete (r as any)[k]
    })
    const result = await saveAnalysisGuidance(props.projectId, next)
    emit('saved', result.configuration)
  } catch (e: any) {
    const detail = e?.response?.data?.detail
    error.value = typeof detail === 'string' ? detail : detail?.message || '配置保存失败，请检查候选、推荐值及版本后重试。'
  } finally { saving.value = false }
}
</script>

<style scoped>
.guidance-editor { max-height: 70vh; overflow: auto; color: #334155; }
label { display: flex; flex-direction: column; gap: 6px; font-size: 13px; margin-bottom: 12px; flex: 1; }
input,select,textarea { border: 1px solid #cbd5e1; border-radius: 6px; padding: 8px; font: inherit; background: #fff; }
button { padding: 7px 12px; border: 1px solid #cbd5e1; border-radius: 6px; background: #f8fafc; cursor: pointer; }
button:disabled { opacity: .5; cursor: default; }
.guidance-columns,.mapping-row,.add-row,.guidance-footer { display: flex; gap: 12px; align-items: start; }
.mapping-row label { flex-direction: row; align-items: center; }
.mapping-row input { flex: 1; }
.operation-guidance { border-top: 1px solid #e2e8f0; padding: 16px 0 4px; }
.guidance-footer { position: sticky; bottom: 0; padding: 12px 0; background: white; justify-content: end; }
.guidance-error { color: #b91c1c; }
</style>
