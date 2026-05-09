// frontend/src/api/knowledge.ts
import client from './client'

export const knowledgeApi = {
  query(projectId: string, question: string, topK = 5) {
    return client.post('/knowledge/query', { project_id: projectId, question, top_k: topK })
  },
  getPages(projectId: string, offset = 0, limit = 50, search?: string) {
    return client.get('/knowledge/pages', { params: { project_id: projectId, offset, limit, search } })
  },
  getPage(projectId: string, pageId: string) {
    return client.get(`/knowledge/pages/${pageId}`, { params: { project_id: projectId } })
  },
  updatePageContent(projectId: string, pageId: string, content: string) {
    return client.put(`/knowledge/pages/${pageId}`, { project_id: projectId, content })
  },
  getPageLinkedPages(projectId: string, pageId: string) {
    return client.get(`/knowledge/pages/${pageId}/links`, { params: { project_id: projectId } })
  },
  searchPages(projectId: string, query: string, limit = 10) {
    return client.get('/knowledge/search', { params: { project_id: projectId, q: query, limit } })
  },
  getIndex(projectId: string) {
    return client.get('/knowledge/index', { params: { project_id: projectId } })
  },
}
