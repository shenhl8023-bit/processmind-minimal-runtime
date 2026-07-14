import type { LocalStepQuestionProfile } from '@/config/analysisQuestionProfileTypes'
import { buildSettingBasisPrompt } from '@/config/sharedRulePromptTemplates'

export const PRECISION_STEP_QUESTION_PROFILES: LocalStepQuestionProfile[] = [
  {
    pattern: /(磨槽|研槽|槽磨|精磨槽|光整槽)/,
    profile: {
      key: 'groove_grinding',
      logicCategory: 'turning_precision',
      directRootValue: 'coverage_reason::requirement',
      rootPrompt: buildSettingBasisPrompt('“磨槽”工序', '槽部技术要求'),
      rootReasonOrder: [
        'coverage_reason::requirement',
        'coverage_reason::structure',
        'coverage_reason::size',
        'coverage_reason::material',
        'coverage_reason::blank',
      ],
      requirementTypePrompt: '这道槽精加工工序存在的条件，主要依赖以下哪类槽部技术要求？',
      requirementTypeOptions: [
        { value: 'precision_type::tolerance', label: '尺寸精度' },
        { value: 'precision_type::roughness', label: '表面粗糙度' },
        { value: 'precision_type::gdt', label: '几何公差' },
      ],
      requirementScopePrompt: '请进一步确认触发“磨槽”工序的槽精度、粗糙度或热后精整要求范围。',
      requirementScopeFallbacks: [
        { value: 'requirement_scope::groove_precision', label: '槽宽、槽深或相关配合尺寸要求较高' },
        { value: 'requirement_scope::groove_gdt', label: '槽侧、槽底或槽位置精度要求较高' },
        { value: 'requirement_scope::groove_roughness', label: '槽表面粗糙度要求较高，需要进一步光整' },
        { value: 'requirement_scope::groove_heat_finish', label: '热处理后需要磨槽恢复尺寸和表面状态' },
      ],
      requirementScopePromptsByType: {
        'requirement_driver::groove_precision': '请进一步确认触发“磨槽”工序的槽宽、槽深或配合尺寸要求范围。',
        'requirement_driver::groove_gdt': '请进一步确认触发“磨槽”工序的槽侧、槽底或槽位置精度要求范围。',
        'requirement_driver::groove_roughness': '请进一步确认触发“磨槽”工序的槽粗糙度或表面质量要求范围。',
        'requirement_driver::groove_heat_finish': '请进一步确认触发“磨槽”工序的热处理后槽尺寸或槽表面状态恢复要求范围。',
        'requirement_driver::groove_fit': '请进一步确认触发“磨槽”工序的关键密封槽、卡簧槽或功能槽要求范围。',
      },
      requirementScopeFallbacksByType: {
        'requirement_driver::groove_precision': [
          { value: 'requirement_scope::groove_precision', label: '槽宽、槽深或相关配合尺寸要求较高' },
        ],
        'requirement_driver::groove_gdt': [
          { value: 'requirement_scope::groove_gdt', label: '槽侧、槽底或槽位置精度要求较高' },
        ],
        'requirement_driver::groove_roughness': [
          { value: 'requirement_scope::groove_roughness', label: '槽表面粗糙度要求较高，需要进一步光整' },
        ],
        'requirement_driver::groove_heat_finish': [
          { value: 'requirement_scope::groove_heat_finish', label: '热处理后需要磨槽恢复尺寸和表面状态' },
        ],
        'requirement_driver::groove_fit': [
          { value: 'requirement_scope::groove_fit', label: '该槽属于关键密封槽、卡簧槽或功能槽' },
        ],
      },
    },
  },
  {
    pattern: /(磨端面|研端面|端面磨)/,
    profile: {
      key: 'face_grinding',
      logicCategory: 'turning_precision',
      directRootValue: 'coverage_reason::requirement',
      rootPrompt: buildSettingBasisPrompt('“磨端面”工序', '端面技术要求'),
      rootReasonOrder: [
        'coverage_reason::requirement',
        'coverage_reason::structure',
        'coverage_reason::size',
        'coverage_reason::material',
        'coverage_reason::blank',
      ],
      requirementTypePrompt: '这道端面精加工工序存在的条件，主要依赖以下哪类端面技术要求？',
      requirementTypeOptions: [
        { value: 'precision_type::tolerance', label: '尺寸精度' },
        { value: 'precision_type::roughness', label: '表面粗糙度' },
        { value: 'precision_type::gdt', label: '几何公差' },
      ],
      requirementScopePrompt: '请进一步确认触发“磨端面”工序的端面精度、贴合或热后精整要求范围。',
      requirementScopeFallbacks: [
        { value: 'requirement_scope::face_flatness', label: '端面平面度、垂直度或端面跳动要求较高' },
        { value: 'requirement_scope::face_length', label: '端面距、总长或尺寸链控制要求较高' },
        { value: 'requirement_scope::face_roughness', label: '端面粗糙度或贴合表面质量要求较高' },
        { value: 'requirement_scope::face_heat_finish', label: '热处理后需要磨端面恢复尺寸和贴合状态' },
      ],
      requirementScopePromptsByType: {
        'requirement_driver::face_flatness': '请进一步确认触发“磨端面”工序的端面平面度、垂直度或端面跳动要求范围。',
        'requirement_driver::face_length': '请进一步确认触发“磨端面”工序的总长、端面距或尺寸链控制要求范围。',
        'requirement_driver::face_roughness': '请进一步确认触发“磨端面”工序的端面粗糙度、贴合或密封表面质量要求范围。',
        'requirement_driver::face_heat_finish': '请进一步确认触发“磨端面”工序的热处理后精整或端面状态恢复要求范围。',
      },
      requirementScopeFallbacksByType: {
        'requirement_driver::face_flatness': [
          { value: 'requirement_scope::face_flatness', label: '端面平面度、垂直度或端面跳动要求较高' },
        ],
        'requirement_driver::face_length': [
          { value: 'requirement_scope::face_length', label: '端面距、总长或尺寸链控制要求较高' },
        ],
        'requirement_driver::face_roughness': [
          { value: 'requirement_scope::face_roughness', label: '端面粗糙度或贴合表面质量要求较高' },
        ],
        'requirement_driver::face_heat_finish': [
          { value: 'requirement_scope::face_heat_finish', label: '热处理后需要磨端面恢复尺寸和贴合状态' },
        ],
      },
    },
  },
  {
    pattern: /(磨外圆|研外圆|精磨外圆|外圆磨|无心磨)/,
    profile: {
      key: 'outer_grinding',
      logicCategory: 'turning_precision',
      directRootValue: 'coverage_reason::requirement',
      rootPrompt: buildSettingBasisPrompt('“磨外圆”工序', '外圆技术要求'),
      rootReasonOrder: [
        'coverage_reason::requirement',
        'coverage_reason::structure',
        'coverage_reason::material',
        'coverage_reason::size',
        'coverage_reason::blank',
      ],
      requirementTypePrompt: '这道外圆精加工工序存在的条件，主要依赖以下哪类外圆技术要求？',
      requirementTypeOptions: [
        { value: 'precision_type::tolerance', label: '尺寸精度' },
        { value: 'precision_type::roughness', label: '表面粗糙度' },
        { value: 'precision_type::gdt', label: '几何公差' },
      ],
      requirementScopePrompt: '请进一步确认触发“磨外圆”工序的精度等级、粗糙度或热后精整要求范围。',
      requirementScopeFallbacks: [
        { value: 'requirement_scope::IT7及以上', label: 'IT7 及以上精度等级' },
        { value: 'requirement_scope::圆度圆柱度跳动', label: '圆度 / 圆柱度 / 跳动要求高' },
        { value: 'requirement_scope::Ra1.6及以上', label: 'Ra1.6 或更高表面质量' },
        { value: 'requirement_scope::热后精整', label: '热处理后仍需精整恢复最终尺寸' },
      ],
      requirementScopePromptsByType: {
        'requirement_driver::outer_precision': '请进一步确认触发“磨外圆”工序的精度等级范围。',
        'requirement_driver::outer_gdt': '请进一步确认触发“磨外圆”工序的圆度、圆柱度、跳动或同轴度要求范围。',
        'requirement_driver::outer_roughness': '请进一步确认触发“磨外圆”工序的粗糙度或表面质量要求范围。',
        'requirement_driver::outer_heat_finish': '请进一步确认触发“磨外圆”工序的热处理后精整要求范围。',
        'requirement_driver::outer_fit': '请进一步确认触发“磨外圆”工序的关键配合面、定尺寸面或功能外圆要求范围。',
      },
      requirementScopeFallbacksByType: {
        'requirement_driver::outer_precision': [
          { value: 'requirement_scope::outer_precision_grade::IT7', label: 'IT7 精度等级' },
          { value: 'requirement_scope::outer_precision_grade::IT6', label: 'IT6 精度等级' },
          { value: 'requirement_scope::outer_precision_grade::IT5+', label: 'IT5 及更高精度等级' },
        ],
        'requirement_driver::outer_gdt': [
          { value: 'requirement_scope::outer_gdt', label: '圆度、圆柱度或跳动要求较高' },
        ],
        'requirement_driver::outer_roughness': [
          { value: 'requirement_scope::outer_roughness', label: '粗糙度要求达到 Ra1.6 或更高表面质量' },
        ],
        'requirement_driver::outer_heat_finish': [
          { value: 'requirement_scope::outer_heat_finish', label: '前面有热处理，需要热后精整恢复尺寸和形位' },
        ],
        'requirement_driver::outer_fit': [
          { value: 'requirement_scope::outer_fit', label: '该外圆属于关键配合面或定尺寸面' },
        ],
      },
    },
  },
  {
    pattern: /(精车外圆|精车.*外圆|外圆精车|精车A侧外圆|精车B侧外圆)/,
    profile: {
      key: 'outer_finish_turning',
      logicCategory: 'turning_precision',
      directRootValue: 'coverage_reason::requirement',
      rootPrompt: buildSettingBasisPrompt('“精车外圆”工序', '外圆技术要求'),
      rootReasonOrder: [
        'coverage_reason::requirement',
        'coverage_reason::structure',
        'coverage_reason::size',
        'coverage_reason::material',
        'coverage_reason::blank',
      ],
      requirementTypePrompt: '这道外圆精加工工序存在的条件，主要依赖以下哪类外圆技术要求？',
      requirementTypeOptions: [
        { value: 'precision_type::tolerance', label: '尺寸精度' },
        { value: 'precision_type::roughness', label: '表面粗糙度' },
        { value: 'precision_type::gdt', label: '几何公差' },
      ],
      requirementScopePrompt: '请进一步确认触发“精车外圆”工序的精度等级、配合或粗糙度要求范围。',
      requirementScopeFallbacks: [
        { value: 'requirement_scope::精度高于IT9', label: '精度等级高于 IT9' },
        { value: 'requirement_scope::关键配合外圆', label: '关键配合外圆或定尺寸外圆' },
        { value: 'requirement_scope::Ra3.2以内', label: '粗糙度进入精车能力范围（如 Ra3.2 及以内）' },
        { value: 'requirement_scope::跳动同轴度较高', label: '跳动 / 同轴度要求较高' },
      ],
      requirementScopePromptsByType: {
        'requirement_driver::turn_precision': '请进一步确认触发“精车外圆”工序的精度等级范围。',
        'requirement_driver::turn_fit': '请进一步确认触发“精车外圆”工序的关键配合、定尺寸或功能外圆要求范围。',
        'requirement_driver::turn_roughness': '请进一步确认触发“精车外圆”工序的粗糙度或表面质量要求范围。',
        'requirement_driver::turn_gdt': '请进一步确认触发“精车外圆”工序的跳动、同轴度、圆度或圆柱度要求范围。',
      },
      requirementScopeFallbacksByType: {
        'requirement_driver::turn_precision': [
          { value: 'requirement_scope::turn_precision_grade::IT9', label: 'IT9 精度等级' },
          { value: 'requirement_scope::turn_precision_grade::IT8', label: 'IT8 精度等级' },
          { value: 'requirement_scope::turn_precision_grade::IT7+', label: 'IT7 及更高精度等级' },
        ],
        'requirement_driver::turn_fit': [
          { value: 'requirement_scope::turn_fit', label: '属于关键配合外圆或定尺寸外圆' },
        ],
        'requirement_driver::turn_roughness': [
          { value: 'requirement_scope::turn_roughness', label: '粗糙度要求已高于半精车稳定能力' },
        ],
        'requirement_driver::turn_gdt': [
          { value: 'requirement_scope::turn_gdt', label: '同轴度、跳动等形位要求已明显提高' },
        ],
      },
    },
  },
  {
    pattern: /(研顶尖孔|研顶尖|修中心孔|精整中心孔)/,
    profile: {
      key: 'center_hole_process',
      logicCategory: 'special',
      directRootValue: 'coverage_reason::structure',
      rootPrompt: buildSettingBasisPrompt('研顶尖/研顶尖孔工序', '中心孔定位或转序条件'),
      rootReasonOrder: [
        'coverage_reason::structure',
        'coverage_reason::requirement',
        'coverage_reason::size',
        'coverage_reason::material',
        'coverage_reason::blank',
      ],
      structureTypePrompt: '这道中心孔精整工序存在的条件，主要依赖以下哪类中心孔定位或转序条件？',
      structureTypeOptions: [
        { value: 'structure_scene::center_datum', label: '装夹定位中心孔或回转基准中心孔' },
        { value: 'structure_scene::center_transfer', label: '粗加工后转序用中心孔或修复中心孔' },
        { value: 'structure_scene::center_precision', label: '高精度顶尖孔或中心孔精整' },
        { value: 'structure_scene::center_protect', label: '避免中心孔损伤、偏摆或重复装夹误差' },
      ],
      structureScopeFallbacks: [
        { value: 'structure_scope::center_datum', label: '主要是在建立装夹定位中心孔或回转基准中心孔' },
        { value: 'structure_scope::center_transfer', label: '主要是在粗加工后修复或转序使用中心孔' },
        { value: 'structure_scope::center_precision', label: '主要是在做高精度顶尖孔或中心孔精整' },
        { value: 'structure_scope::center_protect', label: '主要是在避免中心孔损伤、偏摆或重复装夹误差' },
      ],
      requirementTypePrompt: '如果不是中心孔角色本身，更接近是哪一类定位、跳动或转序质量要求在驱动这道工序？',
      requirementTypeOptions: [
        { value: 'requirement_scene::center_runout', label: '回转跳动、同轴度或装夹重复精度要求' },
        { value: 'requirement_scene::center_transfer', label: '多次装夹转序或热后再定位要求' },
        { value: 'requirement_scene::center_repair', label: '中心孔磨损、损伤或精度恢复要求' },
      ],
      requirementScopePrompt: '请进一步确认触发研顶尖/研顶尖孔工序的定位或转序质量要求范围。',
      requirementScopeFallbacks: [
        { value: 'requirement_scope::center_runout', label: '需要控制回转跳动、同轴度或装夹重复精度' },
        { value: 'requirement_scope::center_transfer', label: '需要满足多次装夹转序或热后再定位' },
        { value: 'requirement_scope::center_repair', label: '需要修复中心孔磨损、损伤或精度状态' },
      ],
    },
  },
  {
    pattern: /(磨孔|研孔|珩孔|精整孔|内圆磨|内孔研磨|内孔磨)/,
    profile: {
      key: 'hole_grinding',
      logicCategory: 'turning_precision',
      directRootValue: 'coverage_reason::requirement',
      rootPrompt: buildSettingBasisPrompt('“磨孔/研孔”工序', '内孔技术要求'),
      rootReasonOrder: [
        'coverage_reason::requirement',
        'coverage_reason::structure',
        'coverage_reason::size',
        'coverage_reason::material',
        'coverage_reason::blank',
      ],
      requirementTypePrompt: '这道内孔精加工工序存在的条件，主要依赖以下哪类内孔精度或配合要求？',
      requirementTypeOptions: [
        { value: 'precision_type::tolerance', label: '尺寸精度' },
        { value: 'precision_type::roughness', label: '表面粗糙度' },
        { value: 'precision_type::gdt', label: '几何公差' },
      ],
      requirementScopePrompt: '请进一步确认触发“磨孔/研孔”工序的孔精度、配合或粗糙度要求范围。',
      requirementScopeFallbacks: [
        { value: 'requirement_scope::孔IT7及以上', label: '孔精度达到 IT7 及以上' },
        { value: 'requirement_scope::孔形位要求高', label: '孔圆度 / 圆柱度 / 位置精度要求高' },
        { value: 'requirement_scope::关键配合孔', label: '关键配合孔或定尺寸孔' },
        { value: 'requirement_scope::孔粗糙度较高', label: '孔粗糙度要求高于精车/精镗稳定能力' },
      ],
      requirementScopePromptsByType: {
        'requirement_driver::hole_precision': '请进一步确认触发“磨孔/研孔”工序的孔精度等级范围。',
        'requirement_driver::hole_gdt': '请进一步确认触发“磨孔/研孔”工序的孔圆度、圆柱度、位置度或同轴度要求范围。',
        'requirement_driver::hole_fit': '请进一步确认触发“磨孔/研孔”工序的关键配合孔、导向孔或定尺寸孔要求范围。',
        'requirement_driver::hole_roughness': '请进一步确认触发“磨孔/研孔”工序的孔表面粗糙度或光整要求范围。',
      },
      requirementScopeFallbacksByType: {
        'requirement_driver::hole_precision': [
          { value: 'requirement_scope::hole_precision_grade::IT7', label: 'IT7 精度等级' },
          { value: 'requirement_scope::hole_precision_grade::IT6', label: 'IT6 精度等级' },
          { value: 'requirement_scope::hole_precision_grade::IT5+', label: 'IT5 及更高精度等级' },
        ],
        'requirement_driver::hole_gdt': [
          { value: 'requirement_scope::hole_gdt', label: '孔圆度、圆柱度或位置精度要求较高' },
          { value: 'requirement_scope::孔形位要求高', label: '孔圆度 / 圆柱度 / 位置精度要求高' },
        ],
        'requirement_driver::hole_fit': [
          { value: 'requirement_scope::hole_fit', label: '该孔属于关键配合孔或定尺寸孔' },
          { value: 'requirement_scope::关键配合孔', label: '关键配合孔或定尺寸孔' },
        ],
        'requirement_driver::hole_roughness': [
          { value: 'requirement_scope::hole_roughness', label: '孔表面粗糙度要求较高，需要进一步光整' },
          { value: 'requirement_scope::孔粗糙度较高', label: '孔粗糙度要求高于精车/精镗稳定能力' },
        ],
      },
    },
  },
]
