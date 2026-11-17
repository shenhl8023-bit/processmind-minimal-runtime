export const secondStepResetCopy = {
  title: '重新推理第二步路线？',
  description: '系统会清除第二步及其后的流程结果，并作废已导入的分组模板。请重新完成路线归并、规则分析和定稿，再生成路线验证；模板映射仍为最后的可选步骤。',
  keepItems: [
    '上传文件',
    '已提取的文档工序明细',
  ],
  clearItems: [
    '第二步归并结果和标准路线',
    '第三步问答与因素审核（需重新回答）',
    '已导入的分组模板文件（需重新导入）',
    '第四步规则定稿及可验证规则（需重新回答、确认）',
    '第五步验证结果（需使用新规则重新生成）',
    '第六步可选模板映射关系（需要时重新完成）',
  ],
  confirmLabel: '确认重新推理',
  busyLabel: '正在启动...',
}

export const thirdStepResetCopy = {
  title: '重新回答第三步全部问题？',
  description: '保留第二步路线和上传资料。第三步重新回答后，请完成第四步规则定稿，再到第五步重新生成路线验证。需要模板映射时，在最后一步重新导入并映射。',
  keepItems: [
    '第二步已保存的标准路线',
    '上传文件和工序明细',
  ],
  clearItems: [
    '第三步全部问答与因素审核（需重新回答）',
    '已导入的分组模板文件（需重新导入）',
    '第四步规则定稿及可验证规则（需重新确认）',
    '第五步已生成路线（需使用新规则重新生成）',
    '第六步可选模板映射关系（需要时重新完成）',
  ],
  confirmLabel: '重新回答全部',
  busyLabel: '正在清理...',
}

export const ruleFinalizeResetCopy = {
  title: '重新识别尚未确认的规则？',
  description: '保留用户条件原文和仍然有效的已确认规则。仅重新识别尚未确认或已失效的规则，完成确认后到第五步使用当前规则重新生成路线验证。',
  keepItems: [
    '用户填写的条件原文',
    '仍然有效的已确认规则（含人工修改）',
    '人工主工序',
    '用户直接设定的 Bool 规则',
    '已完成的模板分组映射',
  ],
  clearItems: [
    '尚未确认或已失效的规则候选（需重新识别、回答并确认）',
    '当前可验证规则版本（需重新保存）',
    '第五步已生成路线（需使用当前规则重新生成）',
  ],
  confirmLabel: '重新识别',
  busyLabel: '正在重新识别...',
}

export function resetCopyForEdition(kind: 'route' | 'analysis' | 'finalize', mappingEnabled = true) {
  const copy = { route: secondStepResetCopy, analysis: thirdStepResetCopy, finalize: ruleFinalizeResetCopy }[kind]
  if (mappingEnabled) return copy
  return {
    ...copy,
    description: kind === 'route'
      ? '系统会清除第二步及其后的流程结果。完成路线归并和规则分析后，需要重新定稿并生成路线验证。'
      : kind === 'analysis'
        ? '保留第二步路线和上传资料。重新回答第三步后，请完成第四步规则定稿，再到第五步生成路线验证。'
        : copy.description,
    keepItems: copy.keepItems.filter(item => !item.includes('模板')),
    clearItems: copy.clearItems.filter(item => !item.includes('模板')),
  }
}
