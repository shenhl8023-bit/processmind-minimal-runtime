import { describe, expect, it } from 'vitest'

import { createBackgroundTaskGuard, runBackgroundTask } from './runBackgroundTask'

function deferred() {
  let resolve!: () => void
  const promise = new Promise<void>((done) => { resolve = done })
  return { promise, resolve }
}

describe('runBackgroundTask', () => {
  it('starts long work without making the caller wait for completion', async () => {
    const task = deferred()
    let started = false
    let completed = false

    const result = runBackgroundTask(async () => {
      started = true
      await task.promise
      completed = true
    })

    expect(result).toBeUndefined()
    expect(started).toBe(true)
    expect(completed).toBe(false)

    task.resolve()
    await Promise.resolve()
    expect(completed).toBe(true)
  })

  it('invalidates an earlier task when the page starts a newer task', () => {
    const guard = createBackgroundTaskGuard()
    const first = guard.start()
    const second = guard.start()

    expect(first.isCurrent()).toBe(false)
    expect(second.isCurrent()).toBe(true)

    guard.cancel()
    expect(second.isCurrent()).toBe(false)
  })
})
