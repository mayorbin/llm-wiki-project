<script setup lang="ts">
/**
 * 知识库主页——源文件管理 + 知识查询 Tab 切换。
 */
import { ref, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { filesApi } from '@/api/files'
import { knowledgeApi } from '@/api/knowledge'
import { renderMarkdown } from '@/lib/markdown'

const route = useRoute()
const projectId = route.params.projectId as string

const activeTab = ref<'files' | 'query'>('files')
const currentDir = ref('')
const dirTree = ref<string[]>([])
const fileList = ref<any[]>([])
const loading = ref(false)

// 查询
const queryText = ref('')
const queryResult = ref('')
const queryLoading = ref(false)

// 删除确认
const deleteTarget = ref<any>(null)
const showDeleteConfirm = ref(false)

// 上传进度
const uploading = ref(false)

async function loadDir() {
  loading.value = true
  try {
    const [dirsRes, filesRes] = await Promise.all([
      filesApi.getDirTree(projectId, currentDir.value),
      filesApi.listFiles(projectId, currentDir.value),
    ])
    dirTree.value = dirsRes.data?.directories || []
    fileList.value = filesRes.data?.files || []
  } catch (e) {
    console.error('加载目录失败:', e)
  } finally {
    loading.value = false
  }
}

async function handleUpload(e: Event) {
  const input = e.target as HTMLInputElement
  if (!input.files?.length) return
  uploading.value = true
  for (const file of Array.from(input.files)) {
    try {
      await filesApi.uploadFile(projectId, currentDir.value, file)
    } catch (e) {
      console.error('上传失败:', e)
    }
  }
  uploading.value = false
  loadDir()
  input.value = ''
}

function confirmDelete(file: any) {
  deleteTarget.value = file
  showDeleteConfirm.value = true
}

async function executeDelete() {
  if (!deleteTarget.value) return
  try {
    const fileId = deleteTarget.value.id || deleteTarget.value.file_id
    await filesApi.deleteFile(fileId, projectId)
  } catch (e) {
    console.error('删除失败:', e)
  }
  showDeleteConfirm.value = false
  deleteTarget.value = null
  loadDir()
}

async function handleQuery() {
  if (!queryText.value.trim()) return
  queryLoading.value = true
  try {
    const res = await knowledgeApi.query(projectId, queryText.value)
    queryResult.value = res.data?.answer || res.data || JSON.stringify(res.data)
  } catch (e: any) {
    queryResult.value = `查询失败: ${e.response?.data?.detail || e.message}`
  } finally {
    queryLoading.value = false
  }
}

function formatFileSize(bytes: number): string {
  if (!bytes) return '-'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

onMounted(loadDir)
watch(() => route.params.projectId, () => { currentDir.value = ''; loadDir() })
</script>

<template>
  <div class="knowledge-page">
    <h2>知识库</h2>

    <div class="tabs">
      <button :class="{ active: activeTab === 'files' }" @click="activeTab = 'files'">📂 源文件</button>
      <button :class="{ active: activeTab === 'query' }" @click="activeTab = 'query'">💬 查询</button>
    </div>

    <!-- 源文件管理 -->
    <div v-if="activeTab === 'files'" class="files-layout">
      <div class="dir-panel">
        <div class="dir-header">📁 目录</div>
        <div class="dir-item" :class="{ active: currentDir === '' }" @click="currentDir = ''; loadDir()">📂 raw/</div>
        <div
          v-for="dir in dirTree" :key="dir" class="dir-item"
          @click="currentDir = dir; loadDir()"
        >📂 {{ dir }}</div>
        <div class="upload-area">
          <label class="upload-label">
            {{ uploading ? '上传中...' : '📤 上传文件' }}
            <input type="file" multiple hidden @change="handleUpload" :disabled="uploading" />
          </label>
        </div>
      </div>

      <div class="file-panel">
        <div class="file-header">
          <span>{{ currentDir || 'raw/' }} ({{ fileList.length }})</span>
        </div>

        <div v-if="fileList.length === 0 && !loading" class="empty-state">
          <div class="empty-icon">📂</div>
          <p>目录为空</p>
          <p class="empty-hint">拖拽文件到此处或点击上传</p>
        </div>

        <table v-else class="file-table">
          <thead>
            <tr><th>文件名</th><th>大小</th><th>状态</th><th>操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="f in fileList" :key="f.id || f.file_id">
              <td>{{ f.filename || f.name }}</td>
              <td class="size">{{ formatFileSize(f.size_bytes || f.size) }}</td>
              <td>
                <span v-if="f.status === 'ingested'" class="badge success">已摄入</span>
                <span v-else-if="f.status === 'ingesting'" class="badge warning">摄入中</span>
                <span v-else class="badge">未摄入</span>
              </td>
              <td class="actions">
                <a :href="`/api/files/${f.id || f.file_id}/download`" class="download-link">下载</a>
                <button class="link-btn danger" @click="confirmDelete(f)">删除</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 知识查询 -->
    <div v-if="activeTab === 'query'" class="query-panel">
      <div class="query-input-row">
        <input v-model="queryText" placeholder="输入问题..." @keyup.enter="handleQuery" class="query-input" />
        <button @click="handleQuery" :disabled="queryLoading" class="query-btn">
          {{ queryLoading ? '查询中...' : '查询' }}
        </button>
      </div>
      <div v-if="queryResult" class="query-result" v-html="renderMarkdown(queryResult, projectId)" />
    </div>

    <!-- 删除确认对话框 -->
    <div v-if="showDeleteConfirm" class="modal-overlay" @click.self="showDeleteConfirm = false">
      <div class="modal">
        <div class="modal-header">⚠ 确认删除</div>
        <div class="modal-body">
          <p>确定要删除 <strong>{{ deleteTarget?.filename || deleteTarget?.name }}</strong> 吗？</p>
          <p class="warning-text">此操作将级联删除关联的 Wiki 页面，且不可撤销。</p>
        </div>
        <div class="modal-footer">
          <button class="cancel-btn" @click="showDeleteConfirm = false">取消</button>
          <button class="delete-btn" @click="executeDelete">确认删除</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.knowledge-page { max-width: 1000px; }

h2 { font-size: 20px; font-weight: 600; margin-bottom: 16px; }

.tabs { display: flex; gap: 4px; margin-bottom: 20px; }

.tabs button {
  padding: 8px 20px;
  background: transparent;
  color: var(--text-secondary);
  border-radius: var(--radius-sm);
  font-size: 13px;
}

.tabs button.active {
  background: var(--bg-card);
  color: var(--accent);
  font-weight: 500;
  box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}

.files-layout { display: flex; gap: 20px; }

.dir-panel {
  width: 200px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
  padding: 12px;
}

.dir-header {
  font-weight: 600;
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.dir-item {
  padding: 6px 8px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  color: var(--text-primary);
}

.dir-item:hover { background: var(--bg-page); }

.dir-item.active { background: var(--bg-page); color: var(--accent); font-weight: 500; }

.upload-area {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border-color);
}

.upload-label {
  display: block;
  width: 100%;
  padding: 8px;
  text-align: center;
  background: var(--accent);
  color: #fff;
  border-radius: var(--radius-sm);
  font-size: 12px;
  cursor: pointer;
}

.file-panel {
  flex: 1;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
  padding: 16px;
  overflow-x: auto;
}

.file-header { font-weight: 500; font-size: 13px; margin-bottom: 12px; }

.empty-state { text-align: center; padding: 48px; color: var(--text-secondary); }

.empty-icon { font-size: 48px; margin-bottom: 12px; }

.empty-hint { font-size: 12px; margin-top: 4px; }

.file-table { width: 100%; border-collapse: collapse; font-size: 13px; }

.file-table th {
  text-align: left;
  padding: 8px 10px;
  border-bottom: 1px solid var(--border-color);
  color: var(--text-secondary);
  font-weight: 500;
  font-size: 11px;
}

.file-table td { padding: 10px; border-bottom: 1px solid var(--bg-page); }

.size { color: var(--text-secondary); }

.badge {
  padding: 2px 10px;
  border-radius: 10px;
  font-size: 11px;
  background: var(--bg-page);
  color: var(--text-secondary);
}

.badge.success { background: var(--success-bg); color: var(--success-text); }

.badge.warning { background: var(--warning-bg); color: var(--warning-text); }

.actions { display: flex; gap: 12px; align-items: center; }

.download-link { font-size: 12px; }

.link-btn { background: transparent; padding: 0; font-size: 12px; }

.link-btn.danger { color: var(--error-text); }

.query-panel { max-width: 700px; }

.query-input-row { display: flex; gap: 8px; margin-bottom: 16px; }

.query-input { flex: 1; padding: 12px 16px; }

.query-btn { padding: 10px 24px; background: var(--accent); color: #fff; }

.query-result {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
  padding: 20px;
}

.query-result :deep(h1),
.query-result :deep(h2),
.query-result :deep(h3) {
  font-size: 15px;
  font-weight: 600;
  margin-top: 16px;
  margin-bottom: 8px;
}

.query-result :deep(p) { margin-bottom: 8px; }

.query-result :deep(a) { color: var(--accent-hover); }

.query-result :deep(blockquote) {
  border-left: 2px solid var(--accent);
  padding-left: 12px;
  color: var(--text-secondary);
  margin: 8px 0;
}

.query-result :deep(code) {
  background: var(--bg-page);
  padding: 1px 4px;
  border-radius: 3px;
  font-size: 12px;
}

.query-result :deep(pre) {
  background: var(--bg-page);
  padding: 12px;
  border-radius: var(--radius-sm);
  overflow-x: auto;
}

.query-result :deep(pre code) { background: transparent; }

.modal-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.3);
  display: flex; align-items: center; justify-content: center; z-index: 100;
}

.modal {
  background: var(--bg-card);
  border-radius: 12px;
  width: 440px;
  overflow: hidden;
  box-shadow: 0 4px 16px rgba(0,0,0,0.12);
}

.modal-header { padding: 16px 20px; font-weight: 600; font-size: 15px; }

.modal-body { padding: 0 20px 16px; font-size: 13px; }

.warning-text { color: var(--error-text); font-size: 12px; margin-top: 8px; }

.modal-footer { display: flex; border-top: 1px solid var(--border-color); }

.modal-footer button { flex: 1; padding: 12px; font-size: 13px; }

.cancel-btn { background: var(--bg-card); color: var(--text-secondary); }

.delete-btn { background: #DC2626; color: #fff; }
</style>
