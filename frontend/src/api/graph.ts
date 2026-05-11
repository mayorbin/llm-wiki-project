// frontend/src/api/graph.ts
/** 图谱 API——匹配后端 /api/graph/data, /api/graph/build, /api/graph/stats */
import client from './client'

export const graphApi = {
  /** 获取已构建的图谱 JSON 数据（nodes + edges + stats） */
  getData(projectId: string) {
    return client.get('/graph/data', { params: { project_id: projectId } })
  },
  /** 触发图谱构建（可选的 LLM 语义推断） */
  build(projectId: string, runInference = false) {
    return client.post('/graph/build', { project_id: projectId, run_inference: runInference })
  },
  /** 获取图谱统计信息（不触发构建） */
  getStats(projectId: string) {
    return client.get('/graph/stats', { params: { project_id: projectId } })
  },
}
