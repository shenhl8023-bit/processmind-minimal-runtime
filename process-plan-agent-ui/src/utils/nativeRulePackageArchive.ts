import type { FinalizedRulePackageResult } from '@/api/extract'
import { textFile, type ArchiveTextFile } from './exportArchive'
import { sampleRulePackageTables, type PublicRulePackageIdentityRegistry } from './sampleRulePackageAdapter'

/** The external protocol is independent of the internally persisted Native V2 tables. */
export function sampleRulePackageFiles(saved: FinalizedRulePackageResult, registry?: PublicRulePackageIdentityRegistry): ArchiveTextFile[] {
  if (!nativeRulePackageFiles(saved)) throw new Error(saved.export_error || '规则包快照不完整，请重新验证并导出。')
  const tables = sampleRulePackageTables(saved, registry)
  return Object.entries(tables).map(([name, table]) => ({ name: `${name}.json`, content: textFile(table) }))
}

/** Export the executable tables; keep analysis evidence in the frozen server snapshot. */
export function nativeRulePackageFiles(saved: FinalizedRulePackageResult): ArchiveTextFile[] | null {
  const sources = saved.export_sources
  const snapshot = sources?.native_snapshot
  const rulePackage = snapshot?.rule_package
  if (saved.export_error || sources?.compiler_version !== 'native-v2/1'
    || snapshot?.schema_version !== '2.0'
    || !Array.isArray(snapshot.normalized_route) || !snapshot.normalized_route.length
    || !rulePackage || !Array.isArray(rulePackage.test_cases)
    || ['manifest', 'factor_dictionary', 'input_schema', 'route_catalog', 'route_rules']
      .some(key => !rulePackage[key] || typeof rulePackage[key] !== 'object' || Array.isArray(rulePackage[key]))) {
    return null
  }
  return [
    { name: 'factor_table.json', content: textFile({
      ...rulePackage.factor_dictionary,
      input_schema: rulePackage.input_schema,
    }) },
    { name: 'full_route_table.json', content: textFile(snapshot.template_mapping_catalog || rulePackage.route_catalog) },
    { name: 'rule_table.json', content: textFile(rulePackage.route_rules) },
  ]
}
