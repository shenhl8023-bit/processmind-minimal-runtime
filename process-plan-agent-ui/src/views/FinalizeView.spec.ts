import { parse } from '@vue/compiler-sfc'
import { describe, expect, it } from 'vitest'
import source from './FinalizeView.vue?raw'

const { descriptor } = parse(source)
const template = descriptor.template?.content || ''
const styles = descriptor.styles.map(style => style.content).join('\n')

describe('finalize review progress summary', () => {
  it('keeps the confirmed rule count without rendering the decorative mini progress bar', () => {
    expect(template).toContain('已确认 <strong>{{ confirmedRuleCount }}/{{ reviewableRuleCount }}</strong>')
    expect(template).not.toContain('mini-progress-bar')
    expect(template).not.toContain('mini-progress-fill')
    expect(styles).not.toContain('.mini-progress-bar')
    expect(styles).not.toContain('.mini-progress-fill')
  })
})
