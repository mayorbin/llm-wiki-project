// frontend/src/api/projects.ts
/** 项目 API——CRUD、成员管理、设置 */
import client from './client'

export const projectsApi = {
  /** 用户所属项目列表 */
  list() {
    return client.get('/projects')
  },
  /** 项目详情 */
  get(projectId: string) {
    return client.get(`/projects/${projectId}`)
  },
  /** 创建项目 */
  create(name: string, description?: string) {
    return client.post('/projects', { name, description: description || '' })
  },
  /** 更新项目基本信息（名称、描述） */
  update(projectId: string, data: Record<string, any>) {
    return client.patch(`/projects/${projectId}`, data)
  },
  /** 删除项目 */
  delete(projectId: string) {
    return client.delete(`/projects/${projectId}`)
  },
  /** 获取项目设置（含 LLM 参数覆盖） */
  getSettings(projectId: string) {
    return client.get(`/projects/${projectId}/settings`)
  },
  /** 更新项目设置 */
  updateSettings(projectId: string, settings: Record<string, any>) {
    return client.patch(`/projects/${projectId}/settings`, settings)
  },
  /** 项目成员列表 */
  getMembers(projectId: string) {
    return client.get(`/projects/${projectId}/members`)
  },
  /** 添加成员 */
  addMember(projectId: string, username: string, role: string) {
    return client.post(`/projects/${projectId}/members`, { username, role })
  },
  /** 移除成员 */
  removeMember(projectId: string, userId: string) {
    return client.delete(`/projects/${projectId}/members/${userId}`)
  },
  /** 转让所有权 */
  transferOwnership(projectId: string, newOwnerId: string) {
    return client.post(`/projects/${projectId}/transfer`, { new_owner_id: newOwnerId })
  },
}
