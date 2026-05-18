// frontend/src/api/files.ts
import client from './client'

export const filesApi = {
  getDirTree(projectId: string, subdir?: string) {
    return client.get('/files/dirs', { params: { project_id: projectId, dir: subdir } })
  },
  createDir(projectId: string, path: string) {
    return client.post('/files/dirs', { project_id: projectId, path })
  },
  deleteDir(projectId: string, path: string) {
    return client.delete('/files/dirs', { data: { project_id: projectId, path } })
  },
  listFiles(projectId: string, dir?: string, search?: string, offset = 0, limit = 50) {
    return client.get('/files', { params: { project_id: projectId, dir, search, offset, limit } })
  },
  uploadFile(projectId: string, subdir: string, file: File, onProgress?: (pct: number) => void) {
    const form = new FormData()
    form.append('project_id', projectId)
    form.append('subdir', subdir)
    form.append('file', file)
    return client.post('/files/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (e) => onProgress?.(Math.round((e.progress ?? 0) * 100)),
    })
  },
  downloadFile(fileId: string) {
    return client.get(`/files/${fileId}/download`, { responseType: 'blob' })
  },
  deleteFile(filePath: string, projectId: string) {
    return client.delete(`/files/${encodeURIComponent(filePath)}`, { params: { project_id: projectId } })
  },
  moveFile(fileId: string, projectId: string, targetSubdir: string) {
    return client.post('/files/move', { file_id: fileId, project_id: projectId, target_subdir: targetSubdir })
  },
  detectChanges(projectId: string) {
    return client.post('/files/detect-changes', { project_id: projectId })
  },
  refresh(projectId: string, fileIds: string[]) {
    return client.post('/files/refresh', { project_id: projectId, file_ids: fileIds })
  },
}
