// frontend/src/api/maintenance.ts
import client from './client'

export const maintenanceApi = {
  /** 获取项目审计日志 */
  getAuditLog(projectId: string, limit = 50) {
    return client.get('/maintenance/audit-log', { params: { project_id: projectId, limit } })
  },

  /** 导出项目备份 */
  exportBackup(projectId: string) {
    return client.get(`/projects/${projectId}/backup`, { responseType: 'blob' })
  },
}
