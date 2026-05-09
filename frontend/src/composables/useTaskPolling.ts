// frontend/src/composables/useTaskPolling.ts
/**
 * 自适应任务轮询 composable——递归 setTimeout，请求不重叠。
 *
 * 轮询间隔根据任务阶段自适应：
 *   queued → 5s
 *   running step 2 (LLM调用) → 2s（最需感知进度）
 *   running other → 3s
 *   running step 5 (图谱) → 5s
 *
 * 网络错误时指数退避（3s → 6s → 12s → 24s → 30s max），成功后重置。
 */

import { ref, onUnmounted } from 'vue'
import { ingestionApi } from '@/api/ingestion'

export interface TaskStatus {
  task_id: string
  status: string
  step?: number
  progress?: number
  error?: any
}

function getPollingInterval(step: number, status: string): number {
  if (status === 'queued') return 5000
  switch (step) {
    case 1: return 3000
    case 2: return 2000
    case 3: case 4: return 3000
    case 5: return 5000
    default: return 3000
  }
}

export function useTaskPolling(taskId: string) {
  const task = ref<TaskStatus | null>(null)
  const error = ref<string | null>(null)
  let timer: ReturnType<typeof setTimeout> | null = null
  let retryCount = 0

  async function poll() {
    try {
      const res = await ingestionApi.getStatus(taskId)
      task.value = res.data
      error.value = null
      retryCount = 0

      const status = res.data?.status || 'queued'
      if (status === 'completed' || status === 'failed' || status === 'rolled_back') {
        return // 终态，停止轮询
      }

      const interval = getPollingInterval(res.data?.step || 0, status)
      timer = setTimeout(poll, interval)
    } catch (e: any) {
      error.value = e.message || '轮询失败'
      retryCount++
      const backoff = Math.min(3000 * Math.pow(2, retryCount), 30000)
      timer = setTimeout(poll, backoff)
    }
  }

  function start() { poll() }
  function stop() { if (timer) { clearTimeout(timer); timer = null } }

  onUnmounted(stop)

  return { task, error, start, stop }
}
