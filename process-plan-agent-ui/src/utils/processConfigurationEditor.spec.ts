import { describe, expect, it } from 'vitest'
import { conditionIsComplete, configurationError, configurationSummary, processRelationDescription } from './processConfigurationEditor'

describe('process configuration editing', () => {
  it('summarizes a legacy trigger without source_match using the any-match default', () => {
    const text = configurationSummary({
      process_id: 'strip', occurrence: 'conditional', when: null,
      relations: [{ relation_type: 'trigger_after', source_process_ids: ['copper', 'inspect'], target_process_ids: ['strip'] }],
    }, '除铜', [], [
      { process_id: 'copper', display_name: '镀铜' },
      { process_id: 'inspect', display_name: '检验' },
    ])
    expect(text).toContain('镀铜或检验任一出现')
    expect(text).not.toContain('全部出现')
  })

  it('accepts nullable condition branches serialized by the backend', () => {
    const leaf:any = {all:null,any:null,not:null,field:'special.requirements',op:'contains',value:'除铜要求'}
    expect(conditionIsComplete(leaf)).toBe(true)
    expect(conditionIsComplete({all:null,any:[leaf],not:null} as any)).toBe(true)
    expect(conditionIsComplete({all:null,any:null,not:leaf} as any)).toBe(true)
  })
  it('rejects empty numeric values without rejecting zero or false', () => {
    expect(conditionIsComplete({field:'diameter', op:'eq', value:''})).toBe(false)
    expect(conditionIsComplete({field:'diameter', op:'eq', value:0})).toBe(true)
    expect(conditionIsComplete({field:'switch', op:'eq', value:false})).toBe(true)
    expect(conditionIsComplete({all:[]})).toBe(false)
    expect(conditionIsComplete({any:[{not:{field:'grade',op:'eq',value:'6061'}}]})).toBe(true)
  })
  it('requires a condition or real trigger and validates each linked process', () => {
    const config:any = {process_id:'strip', occurrence:'conditional', when:null, relations:[]}
    expect(configurationError(config)).toContain('设置出现方式')
    config.relations = [{relation_type:'order_after',source_process_ids:['copper'],target_process_ids:['strip']}]
    expect(configurationError(config)).toContain('设置出现方式')
    expect(configurationError(config)).toContain('仅调整顺序不会带出本工序')
    config.relations[0].relation_type='trigger_after'
    expect(configurationError(config)).toBe('')
    config.relations[0].source_process_ids=[]
    expect(configurationError(config)).toContain('关联工序')
    config.relations[0].source_process_ids=['strip']
    expect(configurationError(config)).toContain('自身')
  })
  it('summarizes field conditions and predecessor triggers as combined gates', () => {
    const config:any = {process_id:'strip', occurrence:'conditional', when:{field:'material',op:'eq',value:'6061'}, relations:[{relation_type:'trigger_after',source_process_ids:['copper'],target_process_ids:['strip'],source_match:'all'}]}
    const text=configurationSummary(config, '除铜', [{key:'material',label:'材料'}] as any, [{process_id:'copper',display_name:'镀铜'}])
    expect(text).toContain('，且')
    expect(text).toContain('镀铜全部出现')
    expect(text).toContain('之后')
    config.occurrence='always'; config.when=null; config.relations[0].relation_type='order_after'
    expect(configurationSummary(config,'除铜',[],[{process_id:'copper',display_name:'镀铜'}])).toContain('都生成时')
  })
  it('explains each relation in plain language using the selected process names', () => {
    const processes:any = [{process_id:'copper', display_name:'镀铜'}, {process_id:'inspect', display_name:'检验'}]
    const relation:any = {source_process_ids:['copper'], source_match:'all'}
    relation.relation_type='trigger_after'
    expect(processRelationDescription(relation, '除铜', processes)).toBe('镀铜纳入路线时，系统会自动纳入除铜，并排在镀铜后；单独设置此关联即可触发，若另设出现条件则需同时满足。')
    relation.relation_type='order_after'
    expect(processRelationDescription(relation, '除铜', processes)).toBe('只管顺序：镀铜和除铜都纳入路线时，除铜排在镀铜后；不会因此自动纳入工序。')
    relation.relation_type='requires'
    expect(processRelationDescription(relation, '除铜', processes)).toBe('除铜纳入路线时，镀铜必须先纳入；系统会尝试补上镀铜，否则提示依赖未满足。')
    relation.relation_type='conflicts'
    expect(processRelationDescription(relation, '除铜', processes)).toBe('除铜和镀铜不能同时纳入；若两者都被选中，系统会提示冲突。')
  })
  it('describes any-match trigger groups accurately', () => {
    const relation:any = {relation_type:'trigger_after', source_process_ids:['copper', 'inspect'], source_match:'any'}
    const text = processRelationDescription(relation, '除铜', [
      {process_id:'copper', display_name:'镀铜'}, {process_id:'inspect', display_name:'检验'},
    ] as any)
    expect(text).toBe('镀铜、检验中的任一工序纳入路线时，系统会自动纳入除铜，并排在镀铜、检验后；单独设置此关联即可触发，若另设出现条件则需同时满足。')
  })
  it('keeps all-match triggers and multiple prerequisites explicit', () => {
    const processes:any = [{process_id:'copper', display_name:'镀铜'}, {process_id:'inspect', display_name:'检验'}]
    expect(processRelationDescription(
      {relation_type:'trigger_after', source_process_ids:['copper', 'inspect'], target_process_ids:['strip'], source_match:'all'},
      '除铜',
      processes,
    )).toContain('镀铜、检验全部纳入路线时')
    expect(processRelationDescription(
      {relation_type:'trigger_after', source_process_ids:['copper', 'inspect'], target_process_ids:['strip']},
      '除铜',
      processes,
    )).toContain('镀铜、检验中的任一工序纳入路线时')
    expect(processRelationDescription(
      {relation_type:'requires', source_process_ids:['copper', 'inspect'], target_process_ids:['strip']},
      '除铜',
      processes,
    )).toContain('镀铜、检验都必须先纳入')
  })
})
