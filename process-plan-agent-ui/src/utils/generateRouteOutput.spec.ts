import { describe, expect, it } from 'vitest'

import { formatGenerateErrorDetail } from './generateRouteOutput'


describe('formatGenerateErrorDetail', () => {
  it('formats structured V2 field errors with labels and allowed values', () => {
    const message = formatGenerateErrorDetail(
      [
        {
          field: 'material.grade',
          reason: '包含未允许值',
          allowed_values: ['9Cr18', '95Cr18'],
        },
      ],
      { 'material.grade': '材料牌号' },
    )

    expect(message).toBe('材料牌号：包含未允许值（可选值：9Cr18、95Cr18）')
  })

  it('uses a safe fallback instead of rendering an object directly', () => {
    expect(formatGenerateErrorDetail({ unexpected: true })).toBe('生成路线失败，请检查输入参数后重试。')
  })
})
