import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const uiRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')

describe('Win7 production build contract', () => {
  it('targets Chromium 109 in the Vite production build', () => {
    const config = readFileSync(resolve(uiRoot, 'vite.config.ts'), 'utf-8')
    expect(config).toContain("target: 'chrome109'")
  })

  it('keeps production API requests same-origin and labels the app', () => {
    const client = readFileSync(resolve(uiRoot, 'src/api/client.ts'), 'utf-8')
    const html = readFileSync(resolve(uiRoot, 'index.html'), 'utf-8')

    expect(client).toContain("return ''")
    expect(html).toContain('<title>ProcessMind</title>')
    expect(html).not.toContain('process-plan-agent-ui')
  })
})
