// frontend/src/api/projects.ts
import client from './client'

export const projectsApi = {
  list() {
    return client.get('/projects')
  },
  get(projectId: string) {
    return client.get(`/projects/${projectId}`)
  },
  create(name: string, description?: string) {
    return client.post('/projects', { name, description })
  },
  update(projectId: string, data: Record<string, any>) {
    return client.put(`/projects/${projectId}`, data)
  },
  delete(projectId: string) {
    return client.delete(`/projects/${projectId}`)
  },
  getSettings(projectId: string) {
    return client.get(`/projects/${projectId}/settings`)
  },
  updateSettings(projectId: string, settings: Record<string, any>) {
    return client.put(`/projects/${projectId}/settings`, settings)
  },
}
