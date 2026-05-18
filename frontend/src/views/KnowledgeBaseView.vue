<script setup lang="ts">
/**
 * 知识库主页——文件管理器 + 知识查询。
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
const queryText = ref('')
const queryResult = ref('')
const queryLoading = ref(false)
const deleteTarget = ref<any>(null)
const showDeleteConfirm = ref(false)
const uploading = ref(false)
const dragOver = ref(false)
const pageStats = ref({ files: 0, pages: 0, lastIngest: '' })

async function loadDir() {
  loading.value = true
  try {
    const [dirsRes, filesRes] = await Promise.all([
      filesApi.getDirTree(projectId, currentDir.value),
      filesApi.listFiles(projectId, currentDir.value),
    ])
    dirTree.value = dirsRes.data?.directories || []
    fileList.value = filesRes.data?.files || []
    pageStats.value.files = fileList.value.length
  } catch (e) { console.error('加载目录失败:', e) }
  finally { loading.value = false }
}

function onDragOver(e: DragEvent) { e.preventDefault(); dragOver.value = true }
function onDragLeave() { dragOver.value = false }
async function onDrop(e: DragEvent) {
  e.preventDefault(); dragOver.value = false
  if (!e.dataTransfer?.files.length) return
  uploading.value = true
  for (const file of Array.from(e.dataTransfer.files)) {
    try { await filesApi.uploadFile(projectId, currentDir.value, file) } catch (e) { console.error(e) }
  }
  uploading.value = false; loadDir()
}

async function handleUpload(e: Event) {
  const input = e.target as HTMLInputElement
  if (!input.files?.length) return
  uploading.value = true
  for (const file of Array.from(input.files)) {
    try { await filesApi.uploadFile(projectId, currentDir.value, file) } catch (e) { console.error(e) }
  }
  uploading.value = false; loadDir()
  input.value = ''
}

function confirmDelete(file: any) { deleteTarget.value = file; showDeleteConfirm.value = true }
async function executeDelete() {
  if (!deleteTarget.value) return
  try { await filesApi.deleteFile(deleteTarget.value.id || deleteTarget.value.file_id, projectId) } catch (e) { console.error(e) }
  showDeleteConfirm.value = false; deleteTarget.value = null; loadDir()
}

async function handleQuery() {
  if (!queryText.value.trim()) return
  queryLoading.value = true
  try {
    const res = await knowledgeApi.query(projectId, queryText.value)
    queryResult.value = res.data?.answer || JSON.stringify(res.data)
  } catch (e: any) {
    queryResult.value = `查询失败: ${e.response?.data?.detail || e.message}`
  } finally { queryLoading.value = false }
}

function formatSize(bytes: number): string {
  if (!bytes) return '-'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1048576) return `${(bytes/1024).toFixed(1)} KB`
  return `${(bytes/1048576).toFixed(1)} MB`
}

function getFileIcon(name: string): string {
  const ext = (name || '').split('.').pop()?.toLowerCase()
  if (ext === 'md') return 'MD'
  if (ext === 'pdf') return 'PDF'
  if (ext === 'docx') return 'DOC'
  if (ext === 'pptx') return 'PPT'
  return 'FILE'
}

onMounted(loadDir)
watch(currentDir, loadDir)
</script>

<template>
  <div class="kb-page">
    <!-- 标签栏 -->
    <div class="tab-bar">
      <button :class="{ active: activeTab === 'files' }" @click="activeTab = 'files'">文件管理</button>
      <button :class="{ active: activeTab === 'query' }" @click="activeTab = 'query'">知识查询</button>
    </div>

    <!-- 文件管理 -->
    <template v-if="activeTab === 'files'">
      <div class="toolbar">
        <div class="dir-breadcrumb">
          <span class="bread-item" :class="{ active: currentDir === '' }" @click="currentDir = ''">raw/</span>
          <template v-if="currentDir">
            <span class="bread-sep">/</span>
            <span class="bread-item active">{{ currentDir }}</span>
          </template>
        </div>
        <div class="toolbar-actions">
          <label class="btn-ghost upload-label">
            <svg viewBox="0 0 20 20" fill="currentColor" width="16"><path d="M3 15a2 2 0 002 2h10a2 2 0 002-2M12 3l4 4-4 4M16 7H6"/></svg>
            上传文件
            <input type="file" multiple hidden @change="handleUpload" :disabled="uploading" />
          </label>
        </div>
      </div>

      <!-- 目录标签 -->
      <div class="dir-tags" v-if="dirTree.length > 0">
        <span class="dir-tags-label">目录：</span>
        <button
          v-for="d in dirTree" :key="d"
          class="dir-tag" :class="{ active: currentDir === d }"
          @click="currentDir = d"
        >{{ d }}</button>
      </div>

      <div class="files-card" :class="{ drag: dragOver }" @dragover="onDragOver" @dragleave="onDragLeave" @drop="onDrop">
        <div class="file-area">
          <div v-if="fileList.length === 0 && !loading" class="empty-state">
            <svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="1.2" opacity="0.25">
              <path d="M12 10h24l8 10v34a2 2 0 01-2 2H12a2 2 0 01-2-2V12a2 2 0 012-2z"/>
              <line x1="16" y1="22" x2="40" y2="22"/><line x1="16" y1="28" x2="32" y2="28"/>
            </svg>
            <h3>此目录为空</h3>
            <p>拖拽文件到此处或点击上传按钮</p>
          </div>

          <table v-else>
            <thead><tr><th>文件</th><th>大小</th><th style="width:80px"></th></tr></thead>
            <tbody>
              <tr v-for="f in fileList" :key="f.id || f.file_id">
                <td>
                  <div class="file-cell">
                    <span class="file-icon">{{ getFileIcon(f.filename || f.name || '') }}</span>
                    <span class="file-name">{{ f.filename || f.name }}</span>
                  </div>
                </td>
                <td class="size-col">{{ formatSize(f.size_bytes || f.size) }}</td>
                <td class="action-col">
                  <button class="btn-ghost" style="font-size:12px;padding:4px 8px" @click="confirmDelete(f)" title="删除">
                    <svg viewBox="0 0 20 20" fill="currentColor" width="14"><path d="M6 4h8v1H6zM7 6h6l-.5 10h-5L7 6zM8 3h4v1H8z" fill-rule="evenodd"/></svg>
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>

    <!-- 知识查询 -->
    <template v-if="activeTab === 'query'">
      <div class="query-area">
        <div class="query-input-row">
          <input v-model="queryText" placeholder="输入问题，例如：这些文档的核心主题是什么？" @keyup.enter="handleQuery" class="query-input" />
          <button class="btn-primary" :disabled="queryLoading" @click="handleQuery">
            {{ queryLoading ? '查询中...' : '查询' }}
          </button>
        </div>
        <div v-if="queryResult" class="query-result card" v-html="renderMarkdown(queryResult, projectId)" />
      </div>
    </template>

    <!-- 删除确认 -->
    <div v-if="showDeleteConfirm" class="modal-overlay" @click.self="showDeleteConfirm = false">
      <div class="modal">
        <div class="modal-header">确认删除</div>
        <div class="modal-body">
          <p>删除 <strong>{{ deleteTarget?.filename || deleteTarget?.name }}</strong> 将级联删除关联的 Wiki 页面，且不可撤销。</p>
        </div>
        <div class="modal-footer">
          <button class="btn-secondary" @click="showDeleteConfirm = false">取消</button>
          <button class="btn-danger" @click="executeDelete">确认删除</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.kb-page { width: 100%; }

.tab-bar { display: flex; gap: 2px; margin-bottom: 20px; background: var(--bg-subtle); border-radius: var(--radius); padding: 3px; width: fit-content; }
.tab-bar button { padding: 7px 20px; background: transparent; color: var(--text-secondary); border-radius: var(--radius-sm); font-size: 13px; font-weight: 500; transition: all var(--transition); }
.tab-bar button.active { background: var(--bg-card); color: var(--text-primary); font-weight: 600; box-shadow: var(--shadow-xs); }

.toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
.dir-breadcrumb { display: flex; align-items: center; gap: 4px; font-size: 14px; }
.bread-item { color: var(--text-muted); cursor: pointer; padding: 2px 6px; border-radius: 4px; transition: all var(--transition); }
.bread-item:hover { color: var(--text-primary); background: var(--bg-subtle); }
.bread-item.active { color: var(--text-primary); font-weight: 600; }
.bread-sep { color: var(--text-muted); font-size: 12px; }
.upload-label { cursor: pointer; }

.dir-tags { display: flex; align-items: center; gap: 6px; margin-bottom: 12px; flex-wrap: wrap; }
.dir-tags-label { font-size: 12px; color: var(--text-muted); font-weight: 500; }
.dir-tag { padding: 4px 12px; border-radius: 100px; font-size: 12px; font-weight: 500; background: var(--bg-subtle); color: var(--text-secondary); border: 1px solid transparent; transition: all var(--transition); }
.dir-tag:hover { background: var(--bg-card); border-color: var(--border); color: var(--text-primary); }
.dir-tag.active { background: var(--accent-light); color: var(--accent); font-weight: 600; border-color: transparent; }

.files-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius-lg); box-shadow: var(--shadow-xs); overflow: hidden; min-height: 340px; transition: border-color var(--transition); }
.files-card.drag { border-color: var(--accent); border-style: dashed; }

.file-area { padding: 16px 20px; min-width: 0; }

.file-cell { display: flex; align-items: center; gap: 10px; }
.file-icon {
  width: 32px; height: 32px; border-radius: var(--radius-sm); background: var(--bg-subtle);
  display: flex; align-items: center; justify-content: center; font-size: 10px;
  font-weight: 700; color: var(--text-muted); flex-shrink: 0;
}
.file-name { font-weight: 500; font-size: 14px; }

.size-col { color: var(--text-muted); font-size: 13px; }
.action-col { text-align: right; }

.query-area { width: 100%; }
.query-input-row { display: flex; gap: 10px; margin-bottom: 16px; }
.query-input { flex: 1; padding: 12px 16px; font-size: 15px; }
.query-result { font-size: 15px; line-height: 1.75; }
.query-result :deep(h2) { font-size: 18px; margin-top: 20px; margin-bottom: 8px; }
.query-result :deep(p) { margin-bottom: 10px; }
.query-result :deep(a) { color: var(--accent); }
.query-result :deep(blockquote) { border-left: 2.5px solid var(--accent); padding-left: 14px; color: var(--text-secondary); margin: 10px 0; }
.query-result :deep(code) { font-size: 12.5px; }
.query-result :deep(pre) { margin: 10px 0; }
</style>
