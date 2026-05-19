// frontend/src/api/ingestion.ts
import client from './client'

export const ingestionApi = {
  trigger(projectId: string, filePaths: string[]) {
    return client.post('/ingestion/trigger', { project_id: projectId, file_paths: filePaths, action: 'ingest' })
  },
  retry(taskId: string) {
    return client.post(`/ingestion/retry/${taskId}`)
  },
  getStatus(taskId: string) {
    return client.get(`/ingestion/status/${taskId}`)
  },
  getStatusBatch(taskIds: string[]) {
    return client.post('/ingestion/statuses', { task_ids: taskIds })
  },
  getHistory(projectId: string, limit = 20) {
    return client.get('/ingestion/history', { params: { project_id: projectId, limit } })
  },
  rollback(taskId: string) {
    return client.post(`/ingestion/rollback/${taskId}`)
  },
}
