import type { TreeOption } from '@/config/analysisQuestionProfileTypes'

export type PrecisionNodeConfig = {
  prompt: string
  sourceHint: string
  options: TreeOption[]
}

export const PRECISION_PRIMARY_CONFIGS: Record<string, PrecisionNodeConfig> = {
  outer_grinding: {
    prompt: '这道外圆精加工工序存在的条件，主要依赖以下哪类外圆技术要求？',
    sourceHint: '先判断主要是外圆尺寸精度、表面粗糙度、几何公差，还是关键配合要求；下一题会按你的选择继续展开。',
    options: [
      { value: 'precision_primary::outer_tolerance', label: '外圆的尺寸精度要求' },
      { value: 'precision_primary::outer_roughness', label: '外圆的表面粗糙度要求' },
      { value: 'precision_primary::outer_gdt', label: '外圆的几何公差要求' },
      { value: 'precision_primary::outer_fit', label: '关键配合外圆要求' },
      { value: 'precision_primary::other_manual', label: '其他要求（需补充说明）' },
    ],
  },
  outer_finish_turning: {
    prompt: '这道外圆精加工工序存在的条件，主要依赖以下哪类外圆技术要求？',
    sourceHint: '先判断主要是外圆尺寸精度、表面粗糙度、几何公差，还是关键配合要求；下一题会按你的选择继续展开。',
    options: [
      { value: 'precision_primary::turn_tolerance', label: '外圆的尺寸精度要求' },
      { value: 'precision_primary::turn_roughness', label: '外圆的表面粗糙度要求' },
      { value: 'precision_primary::turn_gdt', label: '外圆的几何公差要求' },
      { value: 'precision_primary::turn_fit', label: '关键配合外圆要求' },
      { value: 'precision_primary::other_manual', label: '其他要求（需补充说明）' },
    ],
  },
  face_grinding: {
    prompt: '这道端面精加工工序存在的条件，主要依赖以下哪类端面技术要求？',
    sourceHint: '先判断主要是端面尺寸精度、表面粗糙度、几何公差，还是贴合配合要求；下一题会按你的选择继续展开。',
    options: [
      { value: 'precision_primary::face_tolerance', label: '端面的尺寸精度要求' },
      { value: 'precision_primary::face_roughness', label: '端面的表面粗糙度要求' },
      { value: 'precision_primary::face_gdt', label: '端面的几何公差要求' },
      { value: 'precision_primary::face_fit', label: '关键贴合端面要求' },
      { value: 'precision_primary::other_manual', label: '其他要求（需补充说明）' },
    ],
  },
  groove_grinding: {
    prompt: '这道槽精加工工序存在的条件，主要依赖以下哪类槽部技术要求？',
    sourceHint: '先判断主要是槽尺寸精度、表面粗糙度、几何公差，还是功能配合要求；下一题会按你的选择继续展开。',
    options: [
      { value: 'precision_primary::groove_tolerance', label: '槽的尺寸精度要求' },
      { value: 'precision_primary::groove_roughness', label: '槽的表面粗糙度要求' },
      { value: 'precision_primary::groove_gdt', label: '槽的几何公差要求' },
      { value: 'precision_primary::groove_fit', label: '关键功能槽要求' },
      { value: 'precision_primary::other_manual', label: '其他要求（需补充说明）' },
    ],
  },
  hole_default: {
    prompt: '这道内孔精加工工序存在的条件，主要依赖以下哪类内孔精度或配合要求？',
    sourceHint: '先判断主要是内孔尺寸精度、表面粗糙度、几何公差，还是关键配合要求；下一题会按你的选择继续展开。',
    options: [
      { value: 'precision_primary::hole_tolerance', label: '内孔的尺寸精度要求' },
      { value: 'precision_primary::hole_roughness', label: '内孔的表面粗糙度要求' },
      { value: 'precision_primary::hole_gdt', label: '内孔的几何公差要求' },
      { value: 'precision_primary::hole_fit', label: '关键配合孔要求' },
      { value: 'precision_primary::other_manual', label: '其他要求（需补充说明）' },
    ],
  },
}

export const PRECISION_SECONDARY_CONFIGS: Record<string, PrecisionNodeConfig> = {
  'precision_primary::outer_tolerance': {
    prompt: '请进一步确认该工序主要对应的尺寸精度等级范围。',
    sourceHint: '常见按图样尺寸公差或 IT 等级判断；如果工艺文本直接写了公差带、尺寸公差值或配合代号，也优先按最接近的 IT 档位选择。',
    options: [
      { value: 'precision_scope::outer_tolerance::IT8', label: 'IT8' },
      { value: 'precision_scope::outer_tolerance::IT7', label: 'IT7' },
      { value: 'precision_scope::outer_tolerance::IT6', label: 'IT6' },
      { value: 'precision_scope::outer_tolerance::IT5_plus', label: 'IT5及更高' },
      { value: 'precision_scope::other_manual', label: '其他（需补充说明）' },
    ],
  },
  'precision_primary::turn_tolerance': {
    prompt: '请进一步确认该工序主要对应的尺寸精度等级范围。',
    sourceHint: '常见按图样尺寸公差或 IT 等级判断；如果工艺文本直接写了公差带、尺寸公差值或配合代号，也优先按最接近的 IT 档位选择。',
    options: [
      { value: 'precision_scope::turn_tolerance::IT9', label: 'IT9' },
      { value: 'precision_scope::turn_tolerance::IT8', label: 'IT8' },
      { value: 'precision_scope::turn_tolerance::IT7_plus', label: 'IT7及更高' },
      { value: 'precision_scope::other_manual', label: '其他（需补充说明）' },
    ],
  },
  'precision_primary::hole_tolerance': {
    prompt: '请进一步确认该工序主要对应的尺寸精度等级范围。',
    sourceHint: '常见按图样尺寸公差或 IT 等级判断；如果工艺文本直接写了公差带、尺寸公差值或配合代号，也优先按最接近的 IT 档位选择。',
    options: [
      { value: 'precision_scope::hole_tolerance::IT8', label: 'IT8' },
      { value: 'precision_scope::hole_tolerance::IT7', label: 'IT7' },
      { value: 'precision_scope::hole_tolerance::IT6', label: 'IT6' },
      { value: 'precision_scope::hole_tolerance::IT5_plus', label: 'IT5及更高' },
      { value: 'precision_scope::other_manual', label: '其他（需补充说明）' },
    ],
  },
  'precision_primary::face_tolerance': {
    prompt: '请进一步确认该工序主要对应的尺寸精度等级范围。',
    sourceHint: '常见按图样尺寸公差或 IT 等级判断；如果工艺文本直接写了公差带、尺寸公差值或配合代号，也优先按最接近的 IT 档位选择。',
    options: [
      { value: 'precision_scope::surface_tolerance::IT8', label: 'IT8' },
      { value: 'precision_scope::surface_tolerance::IT7', label: 'IT7' },
      { value: 'precision_scope::surface_tolerance::IT6', label: 'IT6' },
      { value: 'precision_scope::surface_tolerance::IT5_plus', label: 'IT5及更高' },
      { value: 'precision_scope::other_manual', label: '其他（需补充说明）' },
    ],
  },
  'precision_primary::groove_tolerance': {
    prompt: '请进一步确认该工序主要对应的尺寸精度等级范围。',
    sourceHint: '常见按图样尺寸公差或 IT 等级判断；如果工艺文本直接写了公差带、尺寸公差值或配合代号，也优先按最接近的 IT 档位选择。',
    options: [
      { value: 'precision_scope::surface_tolerance::IT8', label: 'IT8' },
      { value: 'precision_scope::surface_tolerance::IT7', label: 'IT7' },
      { value: 'precision_scope::surface_tolerance::IT6', label: 'IT6' },
      { value: 'precision_scope::surface_tolerance::IT5_plus', label: 'IT5及更高' },
      { value: 'precision_scope::other_manual', label: '其他（需补充说明）' },
    ],
  },
  'precision_primary::outer_roughness': {
    prompt: '请进一步确认该工序主要对应的表面粗糙度要求范围。',
    sourceHint: '常见按图样中的 Ra 值判断；如果工艺文本写了“光洁度”“表面光洁”或直接给出粗糙度数值，也优先按最接近的 Ra 档位选择。',
    options: [
      { value: 'precision_scope::outer_roughness::Ra1.6', label: 'Ra1.6' },
      { value: 'precision_scope::outer_roughness::Ra0.8', label: 'Ra0.8' },
      { value: 'precision_scope::outer_roughness::Ra0.4', label: 'Ra0.4' },
      { value: 'precision_scope::outer_roughness::Ra0.2_plus', label: 'Ra0.2及更高' },
      { value: 'precision_scope::other_manual', label: '其他（需补充说明）' },
    ],
  },
  'precision_primary::turn_roughness': {
    prompt: '请进一步确认该工序主要对应的表面粗糙度要求范围。',
    sourceHint: '常见按图样中的 Ra 值判断；如果工艺文本写了“光洁度”“表面光洁”或直接给出粗糙度数值，也优先按最接近的 Ra 档位选择。',
    options: [
      { value: 'precision_scope::turn_roughness::Ra3.2', label: 'Ra3.2' },
      { value: 'precision_scope::turn_roughness::Ra1.6', label: 'Ra1.6' },
      { value: 'precision_scope::turn_roughness::Ra0.8', label: 'Ra0.8' },
      { value: 'precision_scope::turn_roughness::Ra0.4_plus', label: 'Ra0.4及更高' },
      { value: 'precision_scope::other_manual', label: '其他（需补充说明）' },
    ],
  },
  'precision_primary::hole_roughness': {
    prompt: '请进一步确认该工序主要对应的表面粗糙度要求范围。',
    sourceHint: '常见按图样中的 Ra 值判断；如果工艺文本写了“光洁度”“表面光洁”或直接给出粗糙度数值，也优先按最接近的 Ra 档位选择。',
    options: [
      { value: 'precision_scope::hole_roughness::Ra1.6', label: 'Ra1.6' },
      { value: 'precision_scope::hole_roughness::Ra0.8', label: 'Ra0.8' },
      { value: 'precision_scope::hole_roughness::Ra0.4', label: 'Ra0.4' },
      { value: 'precision_scope::hole_roughness::Ra0.2_plus', label: 'Ra0.2及更高' },
      { value: 'precision_scope::other_manual', label: '其他（需补充说明）' },
    ],
  },
  'precision_primary::face_roughness': {
    prompt: '请进一步确认该工序主要对应的表面粗糙度要求范围。',
    sourceHint: '常见按图样中的 Ra 值判断；如果工艺文本写了“光洁度”“表面光洁”或直接给出粗糙度数值，也优先按最接近的 Ra 档位选择。',
    options: [
      { value: 'precision_scope::surface_roughness::Ra1.6', label: 'Ra1.6' },
      { value: 'precision_scope::surface_roughness::Ra0.8', label: 'Ra0.8' },
      { value: 'precision_scope::surface_roughness::Ra0.4', label: 'Ra0.4' },
      { value: 'precision_scope::surface_roughness::Ra0.2_plus', label: 'Ra0.2及更高' },
      { value: 'precision_scope::other_manual', label: '其他（需补充说明）' },
    ],
  },
  'precision_primary::groove_roughness': {
    prompt: '请进一步确认该工序主要对应的表面粗糙度要求范围。',
    sourceHint: '常见按图样中的 Ra 值判断；如果工艺文本写了“光洁度”“表面光洁”或直接给出粗糙度数值，也优先按最接近的 Ra 档位选择。',
    options: [
      { value: 'precision_scope::surface_roughness::Ra1.6', label: 'Ra1.6' },
      { value: 'precision_scope::surface_roughness::Ra0.8', label: 'Ra0.8' },
      { value: 'precision_scope::surface_roughness::Ra0.4', label: 'Ra0.4' },
      { value: 'precision_scope::surface_roughness::Ra0.2_plus', label: 'Ra0.2及更高' },
      { value: 'precision_scope::other_manual', label: '其他（需补充说明）' },
    ],
  },
  'precision_primary::outer_gdt': {
    prompt: '请进一步确认该工序主要对应哪些几何公差要求。',
    sourceHint: '外圆类通常优先看圆度、圆柱度、同轴度和跳动；如果工艺文本直接出现这些词，按最接近的项目选择。',
    options: [
      { value: 'precision_scope::outer_gdt::roundness', label: '圆度' },
      { value: 'precision_scope::outer_gdt::cylindricity', label: '圆柱度' },
      { value: 'precision_scope::outer_gdt::coaxiality', label: '同轴度' },
      { value: 'precision_scope::outer_gdt::runout', label: '跳动' },
      { value: 'precision_scope::other_manual', label: '其他（需补充说明）' },
    ],
  },
  'precision_primary::turn_gdt': {
    prompt: '请进一步确认该工序主要对应哪些几何公差要求。',
    sourceHint: '外圆类通常优先看圆度、圆柱度、同轴度和跳动；如果工艺文本直接出现这些词，按最接近的项目选择。',
    options: [
      { value: 'precision_scope::turn_gdt::roundness', label: '圆度' },
      { value: 'precision_scope::turn_gdt::cylindricity', label: '圆柱度' },
      { value: 'precision_scope::turn_gdt::coaxiality', label: '同轴度' },
      { value: 'precision_scope::turn_gdt::runout', label: '跳动' },
      { value: 'precision_scope::other_manual', label: '其他（需补充说明）' },
    ],
  },
  'precision_primary::hole_gdt': {
    prompt: '请进一步确认该工序主要对应哪些几何公差要求。',
    sourceHint: '内孔类通常优先看圆度、圆柱度、同轴度和位置度；如果工艺文本直接出现这些词，按最接近的项目选择。',
    options: [
      { value: 'precision_scope::hole_gdt::roundness', label: '圆度' },
      { value: 'precision_scope::hole_gdt::cylindricity', label: '圆柱度' },
      { value: 'precision_scope::hole_gdt::coaxiality', label: '同轴度' },
      { value: 'precision_scope::hole_gdt::position', label: '位置度' },
      { value: 'precision_scope::other_manual', label: '其他（需补充说明）' },
    ],
  },
  'precision_primary::face_gdt': {
    prompt: '请进一步确认该工序主要对应哪些几何公差要求。',
    sourceHint: '端面类通常优先看平面度、垂直度和跳动；如果工艺文本直接出现这些词，按最接近的项目选择。',
    options: [
      { value: 'precision_scope::face_gdt::flatness', label: '平面度' },
      { value: 'precision_scope::face_gdt::perpendicularity', label: '垂直度' },
      { value: 'precision_scope::face_gdt::runout', label: '跳动' },
      { value: 'precision_scope::other_manual', label: '其他（需补充说明）' },
    ],
  },
  'precision_primary::groove_gdt': {
    prompt: '请进一步确认该工序主要对应哪些几何公差要求。',
    sourceHint: '槽类通常优先看对称度、位置度和侧面平行度；如果工艺文本直接出现这些词，按最接近的项目选择。',
    options: [
      { value: 'precision_scope::groove_gdt::symmetry', label: '对称度' },
      { value: 'precision_scope::groove_gdt::position', label: '位置度' },
      { value: 'precision_scope::groove_gdt::parallelism', label: '侧面平行度' },
      { value: 'precision_scope::other_manual', label: '其他（需补充说明）' },
    ],
  },
  'precision_primary::outer_fit': {
    prompt: '请进一步确认该工序主要对应的配合或功能要求类型。',
    sourceHint: '如果文本里出现间隙、过渡、过盈、导向、密封或定位等描述，优先按最接近的配合类型选择。',
    options: [
      { value: 'precision_scope::fit::clearance', label: '间隙配合' },
      { value: 'precision_scope::fit::transition', label: '过渡配合' },
      { value: 'precision_scope::fit::interference', label: '过盈配合' },
      { value: 'precision_scope::fit::guide_or_seal', label: '密封或导向配合' },
      { value: 'precision_scope::other_manual', label: '其他（需补充说明）' },
    ],
  },
  'precision_primary::turn_fit': {
    prompt: '请进一步确认该工序主要对应的配合或功能要求类型。',
    sourceHint: '如果文本里出现间隙、过渡、过盈、导向、密封或定位等描述，优先按最接近的配合类型选择。',
    options: [
      { value: 'precision_scope::fit::clearance', label: '间隙配合' },
      { value: 'precision_scope::fit::transition', label: '过渡配合' },
      { value: 'precision_scope::fit::interference', label: '过盈配合' },
      { value: 'precision_scope::fit::guide_or_seal', label: '密封或导向配合' },
      { value: 'precision_scope::other_manual', label: '其他（需补充说明）' },
    ],
  },
  'precision_primary::hole_fit': {
    prompt: '请进一步确认该工序主要对应的配合或功能要求类型。',
    sourceHint: '如果文本里出现间隙、过渡、过盈、导向、密封或定位等描述，优先按最接近的配合类型选择。',
    options: [
      { value: 'precision_scope::fit::clearance', label: '间隙配合' },
      { value: 'precision_scope::fit::transition', label: '过渡配合' },
      { value: 'precision_scope::fit::interference', label: '过盈配合' },
      { value: 'precision_scope::fit::guide_or_seal', label: '导向或定位配合' },
      { value: 'precision_scope::other_manual', label: '其他（需补充说明）' },
    ],
  },
  'precision_primary::face_fit': {
    prompt: '请进一步确认该工序主要对应的贴合或配合要求类型。',
    sourceHint: '端面类通常区分贴合、定位贴合和配合端面要求；如果文本里出现贴合面、基准贴合或端面配合，可按最接近类型选择。',
    options: [
      { value: 'precision_scope::face_fit::fit', label: '贴合要求' },
      { value: 'precision_scope::face_fit::datum', label: '定位贴合要求' },
      { value: 'precision_scope::face_fit::pair', label: '配合端面要求' },
      { value: 'precision_scope::other_manual', label: '其他（需补充说明）' },
    ],
  },
  'precision_primary::groove_fit': {
    prompt: '请进一步确认该工序主要对应的功能配合要求类型。',
    sourceHint: '槽类通常区分键配合、卡簧配合和止退功能要求；如果文本里出现键槽、卡簧槽、止退槽等，可按最接近类型选择。',
    options: [
      { value: 'precision_scope::groove_fit::key', label: '键配合' },
      { value: 'precision_scope::groove_fit::retaining', label: '卡簧配合' },
      { value: 'precision_scope::groove_fit::stop', label: '止退功能要求' },
      { value: 'precision_scope::other_manual', label: '其他（需补充说明）' },
    ],
  },
}
