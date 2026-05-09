// frontend/tests/composables/useTaskPolling.test.ts
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useTaskPolling } from '@/composables/useTaskPolling'

// Mock the ingestion API
vi.mock('@/api/ingestion', () => ({
  ingestionApi: {
    getStatus: vi.fn(),
  },
}))

describe('useTaskPolling', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('任务完成后停止轮询', async () => {
    const { ingestionApi } = await import('@/api/ingestion')
    vi.mocked(ingestionApi.getStatus).mockResolvedValue({
      data: { task_id: 't1', status: 'completed' },
    })

    const { start, task } = useTaskPolling('t1')
    start()

    await vi.runAllTimersAsync()

    // 终态——仅调用一次，不再调度新 timer
    expect(ingestionApi.getStatus).toHaveBeenCalledTimes(1)
    expect(task.value?.status).toBe('completed')
  })

  it('运行中任务持续轮询至完成', async () => {
    const { ingestionApi } = await import('@/api/ingestion')
    let callCount = 0
    vi.mocked(ingestionApi.getStatus).mockImplementation(() => {
      callCount++
      return Promise.resolve({
        data: {
          task_id: 't1',
          status: callCount < 3 ? 'running' : 'completed',
          step: 2,
        },
      })
    })

    const { start, task } = useTaskPolling('t1')
    start()

    await vi.runAllTimersAsync()

    // 多次轮询后最终到达 completed 终态，确认停止轮询
    expect(callCount).toBeGreaterThanOrEqual(2)
    expect(task.value?.status).toBe('completed')
  })

  it('网络错误时指数退避后恢复', async () => {
    const { ingestionApi } = await import('@/api/ingestion')

    // 连续两次失败后返回终态（退避间隔 6s → 12s）
    vi.mocked(ingestionApi.getStatus)
      .mockRejectedValueOnce(new Error('网络错误'))
      .mockRejectedValueOnce(new Error('网络错误'))
      .mockResolvedValue({ data: { task_id: 't1', status: 'completed' } })

    const { start, error } = useTaskPolling('t1')
    start()

    await vi.runAllTimersAsync()

    // 退避重试后最终成功，错误清零
    expect(error.value).toBeNull()
    // 至少调用了 3 次（2 次失败 + 1 次成功）
    expect(ingestionApi.getStatus).toHaveBeenCalled()
    const callCount = (ingestionApi.getStatus as any).mock.calls.length
    expect(callCount).toBeGreaterThanOrEqual(3)
  })

  it('stop() 可停止轮询', async () => {
    const { ingestionApi } = await import('@/api/ingestion')
    let callCount = 0
    vi.mocked(ingestionApi.getStatus).mockImplementation(() => {
      callCount++
      return Promise.resolve({
        data: { task_id: 't1', status: 'running', step: 2 },
      })
    })

    const { start, stop } = useTaskPolling('t1')
    start()

    // 让初始 poll 的 Promise 完成（不额外推进时间，只刷新微任务队列）
    await vi.advanceTimersByTimeAsync(1)

    const callsBeforeStop = callCount
    stop()

    // 再推进一段时间——stop 已清除 pending timer，不应再有新调用
    await vi.advanceTimersByTimeAsync(100000)

    expect(callCount).toBe(callsBeforeStop)
  })
})
