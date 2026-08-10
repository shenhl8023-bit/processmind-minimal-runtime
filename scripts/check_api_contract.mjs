import { existsSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const checker = path.join(repoRoot, 'scripts', 'check_api_contract.py')
const bundledPython = path.join(repoRoot, '.runtime', 'python', 'python.exe')
const candidates = [
  ...(existsSync(bundledPython) ? [{ command: bundledPython, prefix: [] }] : []),
  ...(process.platform === 'win32' ? [{ command: 'py', prefix: ['-3'] }] : []),
  { command: 'python3', prefix: [] },
  { command: 'python', prefix: [] },
]

for (const candidate of candidates) {
  const result = spawnSync(candidate.command, [...candidate.prefix, checker, ...process.argv.slice(2)], {
    cwd: repoRoot,
    stdio: 'inherit',
  })
  if (!result.error) process.exit(result.status ?? 1)
  if (result.error.code !== 'ENOENT') throw result.error
}

console.error('No Python 3 runtime was found for the API contract check.')
process.exit(1)
