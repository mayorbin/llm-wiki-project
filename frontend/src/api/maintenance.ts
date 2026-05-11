// frontend/src/api/maintenance.ts
/** 维护 API——审计日志、备份、健康检查 */
import client from './client'

export const maintenanceApi = {
  /** 获取项目审计日志（cursor-based 分页） */
  getAuditLog(projectId: string, limit = 50) {
    return client.get('/audit-log', { params: { project_id: projectId, limit } })
  },
  /** 导出项目备份（返回 tar.gz blob） */
  exportBackup(projectId: string) {
    return client.post('/backup/export', { project_id: projectId }, { responseType: 'blob' })
  },
  /** 导入项目备份 */
  importBackup(projectId: string, file: File) {
    const form = new FormData()
    form.append('project_id', projectId)
    form.append('file', file)
    return client.post('/backup/import', form, { headers: { 'Content-Type': 'multipart/form-data' } })
  },
}
