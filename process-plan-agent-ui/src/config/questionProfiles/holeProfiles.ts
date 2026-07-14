import type { LocalStepQuestionProfile } from '@/config/analysisQuestionProfileTypes'
import { buildSettingBasisPrompt, buildTriggerScopePrompt } from '@/config/sharedRulePromptTemplates'

export const HOLE_STEP_QUESTION_PROFILES: LocalStepQuestionProfile[] = [
  {
    pattern: /(攻螺纹|车螺纹|铣螺纹|套螺纹|螺纹加工)/,
    profile: {
      key: 'thread_process',
      logicCategory: 'turning_coarse',
      skipRequirementScopeAfterType: true,
      directRootValue: 'coverage_reason::structure',
      rootPrompt: buildSettingBasisPrompt('螺纹工序', '螺纹加工对象或技术要求'),
      rootReasonOrder: [
        'coverage_reason::structure',
        'coverage_reason::requirement',
        'coverage_reason::size',
        'coverage_reason::material',
        'coverage_reason::blank',
      ],
      structureTypePrompt: '这道螺纹加工工序存在的条件，主要依赖以下哪类螺纹结构或螺纹加工要求？',
      structureTypeOptions: [
        { value: 'structure_scene::thread_connect', label: '普通连接内螺纹孔或紧固螺纹' },
        { value: 'structure_scene::thread_lock', label: '紧定、锁紧或定位螺纹' },
        { value: 'structure_scene::thread_seal', label: '密封、接头或功能螺纹' },
        { value: 'structure_scene::thread_limit', label: '深孔、小规格或可达性受限螺纹' },
      ],
      structureScopeFallbacks: [
        { value: 'structure_scope::thread_connect', label: '主要是在加工普通连接内螺纹孔或紧固螺纹' },
        { value: 'structure_scope::thread_lock', label: '主要是在加工紧定、锁紧或定位螺纹' },
        { value: 'structure_scope::thread_seal', label: '主要是在加工密封、接头或功能螺纹' },
        { value: 'structure_scope::thread_limit', label: '主要是在处理深孔、小规格或可达性受限螺纹' },
      ],
      requirementTypePrompt: '如果不主要由螺纹结构决定，请确认它存在的条件，主要依赖以下哪类连接、密封或精度需求？',
      requirementTypeOptions: [
        { value: 'requirement_scene::thread_accuracy', label: '螺纹精度、通止规或牙型完整性要求' },
        { value: 'requirement_scene::thread_assembly', label: '装配锁紧、连接强度或重复拆装要求' },
        { value: 'requirement_scene::thread_seal', label: '密封、耐压或介质隔离要求' },
      ],
      requirementScopePrompt: buildTriggerScopePrompt('螺纹工序', '连接或精度要求'),
      requirementScopeFallbacks: [
        { value: 'requirement_scope::thread_accuracy', label: '需要满足螺纹精度、通止规或牙型完整性' },
        { value: 'requirement_scope::thread_assembly', label: '需要满足装配锁紧、连接强度或重复拆装' },
        { value: 'requirement_scope::thread_seal', label: '需要满足密封、耐压或介质隔离要求' },
      ],
    },
  },
  {
    pattern: /(打型孔|割型孔|型孔加工|异形孔加工)/,
    profile: {
      key: 'profile_hole_process',
      logicCategory: 'milling_coarse',
      skipRequirementScopeAfterType: true,
      directRootValue: 'coverage_reason::structure',
      rootPrompt: buildSettingBasisPrompt('打型孔/割型孔工序', '型孔或异形轮廓加工对象'),
      rootReasonOrder: [
        'coverage_reason::structure',
        'coverage_reason::requirement',
        'coverage_reason::size',
        'coverage_reason::material',
        'coverage_reason::blank',
      ],
      structureTypePrompt: '这道型孔或异形轮廓加工工序存在的条件，主要依赖以下哪类加工对象？',
      structureTypeOptions: [
        { value: 'structure_scene::profile_hole', label: '异形轮廓孔、窗口孔或非圆截面孔' },
        { value: 'structure_scene::key_profile', label: '带平边、转角或止转要求的型孔' },
        { value: 'structure_scene::open_profile', label: '局部开口孔、切边孔或边界不封闭型孔' },
        { value: 'structure_scene::compound_profile', label: '复合孔口、沉台联动或多轮廓组合型孔' },
      ],
      structureScopeFallbacks: [
        { value: 'structure_scope::profile_hole', label: '主要是在加工异形轮廓孔、窗口孔或非圆截面孔' },
        { value: 'structure_scope::key_profile', label: '主要是在加工带平边、转角或止转要求的型孔' },
        { value: 'structure_scope::open_profile', label: '主要是在加工局部开口孔、切边孔或边界不封闭型孔' },
        { value: 'structure_scope::compound_profile', label: '主要是在处理复合孔口、沉台联动或多轮廓组合型孔' },
      ],
      requirementTypePrompt: '如果不主要由型孔结构决定，请确认它存在的条件，主要依赖以下哪类轮廓精度、连接或开口边界需求？',
      requirementTypeOptions: [
        { value: 'requirement_scene::profile_precision', label: '型孔轮廓尺寸、边界精度或位置关系要求' },
        { value: 'requirement_scene::profile_fit', label: '止转、配合插入或连接轮廓匹配要求' },
        { value: 'requirement_scene::profile_entry', label: '开口可达性、切边成形或后续装配导入要求' },
      ],
      requirementScopePrompt: buildTriggerScopePrompt('打型孔/割型孔工序', '轮廓精度或连接要求'),
      requirementScopeFallbacks: [
        { value: 'requirement_scope::profile_precision', label: '需要控制型孔轮廓尺寸、边界精度或位置关系' },
        { value: 'requirement_scope::profile_fit', label: '需要满足止转、配合插入或连接轮廓匹配' },
        { value: 'requirement_scope::profile_entry', label: '需要满足开口可达性、切边成形或后续装配导入' },
      ],
    },
  },
  {
    pattern: /(钻孔|镗孔|铰孔|钻镗孔|钻铰孔|攻螺纹|中心孔|中间通孔|打孔|打型孔|割型孔|研顶尖孔|研顶尖)/,
    profile: {
      key: 'hole_process_general',
      logicCategory: 'turning_coarse',
      skipRequirementScopeAfterType: true,
      directRootValue: 'coverage_reason::structure',
      rootPrompt: buildSettingBasisPrompt('孔加工工序', '孔加工对象或前道加工要求'),
      rootReasonOrder: [
        'coverage_reason::structure',
        'coverage_reason::requirement',
        'coverage_reason::size',
        'coverage_reason::material',
        'coverage_reason::blank',
      ],
      structureTypePrompt: '这道孔加工工序存在的条件，主要依赖以下哪类孔结构或前道孔加工要求？',
      structureTypeOptions: [
        { value: 'structure_scene::through_hole', label: '通孔、普通孔或一般孔结构' },
        { value: 'structure_scene::deep_hole', label: '深孔、长孔或可达性受限孔' },
        { value: 'structure_scene::center_hole', label: '中心孔、定位孔或装夹基准孔' },
        { value: 'structure_scene::compound_hole', label: '阶梯孔、复合孔或带孔口特征的孔' },
      ],
      structureScopeFallbacks: [
        { value: 'structure_scope::through_hole', label: '主要是在加工通孔、普通孔或一般孔结构' },
        { value: 'structure_scope::deep_hole', label: '主要是在加工深孔、长孔或可达性受限孔' },
        { value: 'structure_scope::center_hole', label: '主要是在加工中心孔、定位孔或装夹基准孔' },
        { value: 'structure_scope::compound_hole', label: '主要是在加工阶梯孔、复合孔或带孔口特征的孔' },
      ],
      requirementTypePrompt: '如果不主要由孔结构决定，请确认它存在的条件，主要依赖以下哪类孔尺寸基础、后续精加工准备或加工边界需求？',
      requirementTypeOptions: [
        { value: 'requirement_scene::hole_precision', label: '需要先控制孔径、孔深或孔位的基础尺寸' },
        { value: 'requirement_scene::hole_fit', label: '需要为后续镗孔、铰孔或磨孔预留稳定余量' },
        { value: 'requirement_scene::hole_access', label: '排屑、可达性或双向加工边界要求' },
      ],
      requirementScopePrompt: buildTriggerScopePrompt('孔加工工序', '孔尺寸基础或孔边界需求'),
      requirementScopeFallbacks: [
        { value: 'requirement_scope::hole_precision', label: '需要先控制孔径、孔深或孔位的基础尺寸' },
        { value: 'requirement_scope::hole_fit', label: '需要为后续镗孔、铰孔或磨孔预留稳定余量' },
        { value: 'requirement_scope::hole_access', label: '需要满足排屑、可达性或双向加工边界' },
      ],
    },
  },
]
