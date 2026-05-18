// frontend/src/api/maintenance.ts
/** 维护 API——审计日志、备份。使用独立 axios 实例避免拦截器问题。 */
import axios from 'axios'

const raw = axios.create({
  baseURL: '/api',
  timeout: 10000,
  headers: { 'Content-Type': 'application/json' },
})

// 请求拦截：注入 JWT（不触发 activeRequests 计数器）
raw.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截：不自动刷新 Token，只做错误传递
raw.interceptors.response.use(
  (res) => res,
  (err) => Promise.reject(err),
)

export const maintenanceApi = {
  getAuditLog(projectId: string, limit = 50) {
    return raw.get('/audit-log', { params: { project_id: projectId, limit } })
  },
  exportBackup(projectId: string) {
    return raw.post('/backup/export', { project_id: projectId }, { responseType: 'blob' })
  },
  importBackup(projectId: string, file: File) {
    const form = new FormData()
    form.append('project_id', projectId)
    form.append('file', file)
    return raw.post('/backup/import', form, { headers: { 'Content-Type': 'multipart/form-data' } })
  },
}
