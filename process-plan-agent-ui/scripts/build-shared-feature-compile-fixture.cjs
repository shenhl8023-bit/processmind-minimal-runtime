// Run from the UI directory after changing this cross-language integration path.
const fs = require('fs')
const path = require('path')
const crypto = require('crypto')
const esbuild = require('esbuild')
const root = path.resolve(__dirname, '../..')
const source = 'process-plan-agent-ui/src/utils/__fixtures__/sharedFeatureCompile.ts'
const result = esbuild.buildSync({ entryPoints: [path.join(root, source)], bundle: true, write: false,
  platform: 'node', format: 'cjs', alias: { '@': path.join(root, 'process-plan-agent-ui/src') } })
const fixtureModule = { exports: {} }
new Function('module', 'exports', result.outputFiles[0].text)(fixtureModule, fixtureModule.exports)
const cases = fixtureModule.exports.buildSharedFeatureCompileCases()
const dependencies = [source, 'process-plan-agent-ui/src/utils/finalizeRulePackage.ts',
  'process-plan-agent-ui/src/utils/featureInputProjection.ts', 'process-plan-agent-ui/src/utils/projectConditionFields.ts',
  'process-plan-agent-ui/src/composables/analysisGuidanceFlow.ts', 'process-plan-agent-ui/src/composables/analysisGuidedObjects.ts',
  'process-plan-agent-api/app/assets/project_conditions.json']
const provenance = { engine: 'actual TS question/editor definitions and finalize builder, executed by Node',
  generator: 'process-plan-agent-ui/scripts/build-shared-feature-compile-fixture.cjs',
  dependencies: dependencies.map(source => ({ source, sha256: crypto.createHash('sha256').update(fs.readFileSync(path.join(root, source))).digest('hex') })) }
fs.writeFileSync(path.join(root, 'process-plan-agent-api/tests/fixtures/shared_feature_compile_requests.json'),
  JSON.stringify({ provenance, cases }, null, 2) + '\n')
console.log(`Generated ${cases.length} actual compile requests`)
