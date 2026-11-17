import { defineConfig, mergeConfig } from 'vitest/config'
import applicationConfig from './vite.config'

export default defineConfig(env => mergeConfig(applicationConfig(env), {
  test: {
    // Vitest otherwise replaces CSS imports, including ?raw, with empty strings.
    css: { include: [/\/styles\/global\.css\?raw$/] },
  },
}))
