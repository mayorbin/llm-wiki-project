// frontend/src/api/knowledge.ts
/** 知识 API——查询、页面浏览、编辑 */
import client from './client'

export const knowledgeApi = {
  /** LLM 综合回答（附 [[wikilinks]] 引用） */
  query(projectId: string, question: string, model?: string) {
    return client.post('/knowledge/query', { project_id: projectId, question, model }, { timeout: 300000 })
  },
  /** 流式查询——返回 fetch Response，调用方通过 reader 逐条读取 SSE 事件 */
  queryStream(projectId: string, question: string, model?: string) {
    const token = localStorage.getItem('access_token')
    const params = new URLSearchParams({ project_id: projectId, question })
    if (model) params.set('model', model)
    return fetch(`/api/knowledge/query/stream?${params}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
  },
  /** Wiki 页面树（按类型分组） */
  getPages(projectId: string, type?: string) {
    return client.get('/knowledge/pages', { params: { project_id: projectId, type } })
  },
  /** 读取单个页面 markdown 内容 */
  getPage(projectId: string, pagePath: string) {
    return client.get(`/knowledge/pages/${encodeURIComponent(pagePath)}`, { params: { project_id: projectId } })
  },
  /** 编辑页面内容 */
  updatePage(projectId: string, pagePath: string, content: string) {
    return client.put(`/knowledge/pages/${encodeURIComponent(pagePath)}`, { project_id: projectId, content })
  },
  /** 页面编辑历史 */
  getPageHistory(projectId: string, pagePath: string) {
    return client.get(`/knowledge/pages/${encodeURIComponent(pagePath)}/history`, { params: { project_id: projectId } })
  },
}
