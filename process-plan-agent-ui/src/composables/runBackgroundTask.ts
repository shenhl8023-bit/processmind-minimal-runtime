export function runBackgroundTask(task: () => Promise<void>, onError?: (error: unknown) => void) {
  try {
    void task().catch((error: unknown) => {
      onError?.(error)
    })
  } catch (error) {
    onError?.(error)
  }
}

export function createBackgroundTaskGuard() {
  let taskId = 0

  return {
    start() {
      taskId += 1
      const currentTaskId = taskId
      return {
        isCurrent: () => currentTaskId === taskId,
      }
    },
    cancel() {
      taskId += 1
    },
  }
}
