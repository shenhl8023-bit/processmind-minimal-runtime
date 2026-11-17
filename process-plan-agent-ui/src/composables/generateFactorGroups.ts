import type { GenerateInputField } from './useGenerateInputFields'
import { projectConditionScope } from '@/utils/projectConditionFields'
import { featureCategories, sharedFeatureField } from '@/utils/featureInputProjection'
export { actualProjectItGrades, isActualProjectItField } from '@/utils/projectConditionFields'

export const isMaterialInput = (field: GenerateInputField) => /^(?:material\.)|\.material_grade$/.test(field.key) || /材料牌号/.test(field.name || '')
export const isManualInput = (field: GenerateInputField) => field.key.startsWith('project_factor.manual_process_') && field.source === '用户直接设定'

export type FactorProcessDefinition = { process_id: string; display_name: string }
export type FeatureInputItem = { name: string; presenceKey: string; fields: GenerateInputField[] }
type FactorGroup = { id: string; title: string; context: string; fields: GenerateInputField[]; features?: FeatureInputItem[] }

export function groupGenerateFields(fields: GenerateInputField[], processes: FactorProcessDefinition[] = []) {
  const namesByScope = new Map(processes.map(process => [projectConditionScope(process.process_id), process.display_name]))
  const sections = [
    { id: 'basic', title: '基本信息（材料）', groups: [] as FactorGroup[] },
    { id: 'machining', title: '加工因素（特征、方位、精度）', groups: [] as FactorGroup[] },
    { id: 'manual', title: '人工安排', groups: [] as FactorGroup[] },
  ]
  for (const field of fields) {
    const feature = sharedFeatureField.exec(field.key)
    if (feature) {
      if (feature[2] !== 'present') continue
      const name = field.name || field.key
      const category = featureCategories.find(category => category.names.includes(name)) || featureCategories[featureCategories.length - 1]!
      const section = sections[1]!
      let group = section.groups.find(group => group.id === category.id)
      if (!group) {
        group = { id: category.id, title: category.title, context: '', fields: [], features: [] }
        section.groups.push(group)
      }
      group.features!.push({ name, presenceKey: field.key, fields: fields.filter(parameter => parameter.key.startsWith(`${feature[1]}.`) && parameter.key !== field.key) })
      continue
    }
    const section = sections[isMaterialInput(field) ? 0 : isManualInput(field) ? 2 : 1]!
    const scope = field.key.match(/^(project_factor\.operation_[^.]+)\./)?.[1] || section.id
    let group = section.groups.find(g => g.id === scope)
    if (!group) {
      const name = field.name || ''
      const object = name.split(' · ').slice(-1)[0]?.match(/^(.+)的实际/)?.[1]
      const legacyTitle = name.split(' · ')[0]!.replace(/加工对象的特征.*|同一加工对象的方位.*|目标硬度.*|当前部位是否有明确/g, '').replace(/要求$/, '')
      group = { id: scope, title: scope === section.id ? '' : namesByScope.get(scope) || legacyTitle, context: object ? `加工特征：${object}（已确定）` : '', fields: [] }
      section.groups.push(group)
    }
    group.fields.push(field)
  }
  const rank = new Map(featureCategories.map((category, index) => [category.id, index]))
  sections[1]!.groups.sort((a, b) => (rank.get(a.id) ?? 99) - (rank.get(b.id) ?? 99))
  return sections.filter(section => section.groups.length)
}
