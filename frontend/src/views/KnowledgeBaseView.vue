<script setup lang="ts">
/**
 * 知识库主页——文件管理器 + 知识查询。
 */
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { filesApi } from '@/api/files'
import { knowledgeApi } from '@/api/knowledge'
import { renderMarkdown } from '@/lib/markdown'

const route = useRoute()
const projectId = route.params.projectId as string

const activeTab = ref<'files' | 'query'>('files')
const currentDir = ref('')
const dirTree = ref<any[]>([])
const fileList = ref<any[]>([])
const loading = ref(false)
const queryText = ref('')
const queryResult = ref('')
const queryLoading = ref(false)
const deleteTarget = ref<any>(null)
const showDeleteConfirm = ref(false)
const uploading = ref(false)
const dragOver = ref(false)

// 展开状态：默认展开根目录（path='' 即"全部文件"）
const expandedDirs = ref<Set<string>>(new Set(['']))

// 扁平化目录列表：始终包含"全部文件"根节点，其下为子目录
const flatDirs = computed(() => {
  const result: { name: string; path: string; depth: number; hasChildren: boolean }[] = []
  const rootHasChildren = dirTree.value.some((n: any) => n.type === 'directory')
  result.push({ name: '全部文件', path: '', depth: 0, hasChildren: rootHasChildren })
  if (expandedDirs.value.has('')) {
    function walk(nodes: any[], depth: number) {
      for (const n of nodes) {
        if (n.type !== 'directory') continue
        const hasChildren = (n.children || []).some((c: any) => c.type === 'directory')
        result.push({ name: n.name, path: n.path, depth, hasChildren })
        if (expandedDirs.value.has(n.path)) {
          walk(n.children || [], depth + 1)
        }
      }
    }
    walk(dirTree.value, 1)
  }
  return result
})

function toggleDir(path: string) {
  const next = new Set(expandedDirs.value)
  if (next.has(path)) next.delete(path)
  else next.add(path)
  expandedDirs.value = next
}

async function loadDir() {
  loading.value = true
  try {
    const [dirsRes, filesRes] = await Promise.all([
      filesApi.getDirTree(projectId, currentDir.value),
      filesApi.listFiles(projectId, currentDir.value),
    ])
    dirTree.value = dirsRes.data?.directories || []
    fileList.value = filesRes.data?.files || []
  } catch (e) { console.error(e) }
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
  try { await filesApi.deleteFile(deleteTarget.value.path, projectId) } catch (e) { console.error(e) }
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

function formatDate(iso: string): string {
  if (!iso) return '-'
  return iso.slice(0, 10).replace(/^\d{4}-/, '')  // "05-18"
}

function getFileExt(name: string): string {
  return (name || '').split('.').pop()?.toLowerCase() || ''
}

function getFileStem(name: string): string {
  return (name || '').replace(/\.[^.]+$/, '')
}

onMounted(loadDir)
watch(currentDir, loadDir)
</script>

<template>
  <div class="kb-page">
    <div class="tab-bar">
      <button :class="{ active: activeTab === 'files' }" @click="activeTab = 'files'">文件管理</button>
      <button :class="{ active: activeTab === 'query' }" @click="activeTab = 'query'">知识查询</button>
    </div>

    <template v-if="activeTab === 'files'">
      <div class="fm-toolbar">
        <div class="fm-path">
          <svg class="fm-path-icon" viewBox="0 0 20 20" fill="currentColor" width="15"><path d="M2 5a2 2 0 012-2h3.6c.4 0 .8.2 1 .5L10 5h6a2 2 0 012 2v8a2 2 0 01-2 2H4a2 2 0 01-2-2V5z"/></svg>
          <span class="fm-path-item" :class="{ on: currentDir === '' }" @click="currentDir = ''">全部文件</span>
          <template v-if="currentDir">
            <span class="fm-path-arrow">›</span>
            <span class="fm-path-item on">{{ currentDir }}</span>
          </template>
        </div>
        <div class="fm-actions">
          <span class="fm-count" v-if="fileList.length">{{ fileList.length }} 个文件</span>
          <label class="btn-primary btn-sm">
            <svg viewBox="0 0 20 20" fill="currentColor" width="15"><path d="M10 3v12M4 10h12" stroke="currentColor" stroke-width="2" fill="none"/></svg>
            上传文件
            <input type="file" multiple hidden @change="handleUpload" :disabled="uploading" />
          </label>
        </div>
      </div>

      <div class="fm-body">
        <nav class="fm-sidebar">
          <div class="fm-sidebar-label">目录</div>
          <div
            v-for="d in flatDirs"
            :key="d.path"
            class="tree-node"
            :class="{ active: currentDir === d.path, root: d.depth === 0 }"
            :style="{ paddingLeft: (d.depth * 14 + 11) + 'px' }"
            @click="currentDir = d.path"
          >
            <span
              v-if="d.hasChildren"
              class="tree-chevron"
              :class="{ expanded: expandedDirs.has(d.path) }"
              @click.stop="toggleDir(d.path)"
            >
              <svg viewBox="0 0 20 20" fill="currentColor" width="12"><path d="M7 5l5 5-5 5" stroke="currentColor" stroke-width="2" fill="none"/></svg>
            </span>
            <span v-else class="tree-chevron-spacer" />
            <svg class="tree-icon" viewBox="0 0 20 20" fill="currentColor" width="14"><path d="M2 5a2 2 0 012-2h3.6c.4 0 .8.2 1 .5L10 5h6a2 2 0 012 2v8a2 2 0 01-2 2H4a2 2 0 01-2-2V5z"/></svg>
            <span class="tree-name">{{ d.name }}</span>
          </div>
        </nav>

        <div class="fm-main" :class="{ drag: dragOver }" @dragover="onDragOver" @dragleave="onDragLeave" @drop="onDrop">
          <div v-if="fileList.length === 0 && !loading" class="empty-state">
            <svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="1.2" opacity="0.2" width="48">
              <path d="M8 6h18l6 8v28a2 2 0 01-2 2H8a2 2 0 01-2-2V8a2 2 0 012-2z"/>
            </svg>
            <p>目录为空，拖拽文件或点击上传</p>
          </div>
          <table v-else>
            <thead><tr><th>文件名</th><th>大小</th><th>修改日期</th><th></th></tr></thead>
            <tbody>
              <tr v-for="f in fileList" :key="f.name">
                <td>
                  <div class="file-cell">
                    <span class="file-ext" :class="getFileExt(f.name)">{{ getFileExt(f.name) }}</span>
                    <span class="file-stem">{{ getFileStem(f.name) }}</span>
                  </div>
                </td>
                <td class="size-col">{{ formatSize(f.size_bytes) }}</td>
                <td class="date-col">{{ formatDate(f.modified_at) }}</td>
                <td class="action-col">
                  <button class="btn-ghost" style="padding:4px 6px" @click="confirmDelete(f)" title="删除">
                    <svg viewBox="0 0 20 20" fill="currentColor" width="14"><path d="M6 4h8v1H6zM7 6h6l-.5 10h-5L7 6zM8 3h4v1H8z" fill-rule="evenodd"/></svg>
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>

    <template v-if="activeTab === 'query'">
      <div class="query-area">
        <div class="query-input-row">
          <input v-model="queryText" placeholder="输入问题，例如：这些文档的核心主题是什么？" @keyup.enter="handleQuery" class="query-input" />
          <button class="btn-primary" :disabled="queryLoading" @click="handleQuery">{{ queryLoading ? '查询中...' : '查询' }}</button>
        </div>
        <div v-if="queryResult" class="query-result card" v-html="renderMarkdown(queryResult, projectId)" />
      </div>
    </template>

    <div v-if="showDeleteConfirm" class="modal-overlay" @click.self="showDeleteConfirm = false">
      <div class="modal">
        <div class="modal-header">确认删除</div>
        <div class="modal-body"><p>删除 <strong>{{ deleteTarget?.filename || deleteTarget?.name }}</strong> 将级联删除关联的 Wiki 页面，且不可撤销。</p></div>
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

/* toolbar */
.fm-toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 0; padding: 10px 18px; background: var(--bg-card); border: 1px solid var(--border); border-bottom: none; border-radius: var(--radius-lg) var(--radius-lg) 0 0; }
.fm-path { display: flex; align-items: center; gap: 4px; }
.fm-path-icon { color: var(--text-muted); margin-right: 2px; }
.fm-path-item { font-size: 13px; color: var(--text-muted); cursor: pointer; padding: 3px 8px; border-radius: var(--radius-sm); transition: all var(--transition); }
.fm-path-item:hover { color: var(--text-primary); background: var(--bg-subtle); }
.fm-path-item.on { color: var(--text-primary); font-weight: 600; }
.fm-path-arrow { color: var(--text-muted); font-size: 16px; }

.fm-actions { display: flex; align-items: center; gap: 12px; }
.fm-count { font-size: 12px; color: var(--text-muted); }
.btn-sm { padding: 6px 14px; font-size: 13px; }

/* body */
.fm-body { display: flex; background: var(--bg-card); border: 1px solid var(--border); border-top: none; border-radius: 0 0 var(--radius-lg) var(--radius-lg); min-height: 400px; overflow: hidden; }

.fm-sidebar { width: 200px; min-width: 0; border-right: 1px solid var(--border-light); padding: 14px 0; flex-shrink: 0; overflow-y: auto; }
.fm-sidebar-label { font-size: 11px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; padding: 0 14px 8px; }

/* directory tree nodes */
.tree-node {
  display: flex; align-items: center; gap: 5px;
  padding: 6px 12px 6px 11px;
  font-size: 13px; color: var(--text-secondary);
  cursor: pointer; transition: all var(--transition); user-select: none;
}
.tree-node.root { font-weight: 500; color: var(--text-primary); }
.tree-node:hover { background: var(--bg-subtle); color: var(--text-primary); }
.tree-node.active { background: var(--accent-light); color: var(--accent); font-weight: 600; }
.tree-node.active .tree-icon { color: var(--accent); }
.tree-chevron {
  display: flex; align-items: center; justify-content: center;
  width: 16px; height: 16px; flex-shrink: 0;
  color: var(--text-muted); transition: transform var(--transition);
}
.tree-chevron.expanded { transform: rotate(90deg); }
.tree-chevron-spacer { width: 16px; flex-shrink: 0; }
.tree-icon { color: var(--text-muted); flex-shrink: 0; }
.tree-name { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

.fm-main { flex: 1; padding: 0; min-width: 0; transition: border-color var(--transition); }
.fm-main.drag { background: var(--accent-light); }

.empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 80px 32px; text-align: center; color: var(--text-muted); }
.empty-state p { font-size: 14px; margin-top: 14px; }

table { width: 100%; border-collapse: collapse; }
thead th { text-align: left; padding: 10px 18px; border-bottom: 2px solid var(--border); color: var(--text-muted); font-weight: 500; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; }
tbody td { padding: 11px 18px; border-bottom: 1px solid var(--border-light); }
tbody tr:hover { background: var(--bg-subtle); }
tbody tr:last-child td { border-bottom: none; }

.file-cell { display: flex; align-items: center; gap: 8px; }
.file-ext {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 32px; padding: 2px 7px; border-radius: 4px;
  font-size: 10.5px; font-weight: 700; text-transform: uppercase;
  background: var(--bg-subtle); color: var(--text-muted);
}
.file-ext.pdf { background: #FEF2F2; color: #DC2626; }
.file-ext.md { background: #F0FDF4; color: #16A34A; }
.file-ext.docx, .file-ext.doc { background: #EFF6FF; color: #2563EB; }
.file-ext.pptx, .file-ext.ppt { background: #FFF7ED; color: #EA580C; }
.file-ext.xlsx, .file-ext.xls, .file-ext.csv { background: #F0FDF4; color: #059669; }
.file-ext.jpg, .file-ext.png, .file-ext.gif, .file-ext.svg { background: #FAF5FF; color: #7C3AED; }

.file-stem { font-weight: 500; font-size: 14px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 360px; }
.size-col { color: var(--text-muted); font-size: 13px; white-space: nowrap; }
.date-col { color: var(--text-muted); font-size: 12px; white-space: nowrap; }
.action-col { text-align: right; }

.query-area { width: 100%; max-width: 780px; }
.query-input-row { display: flex; gap: 10px; margin-bottom: 16px; }
.query-input { flex: 1; padding: 12px 16px; font-size: 15px; }
.query-result { font-size: 15px; line-height: 1.75; }
.query-result :deep(h2) { font-size: 18px; margin-top: 20px; margin-bottom: 8px; }
.query-result :deep(p) { margin-bottom: 10px; }
.query-result :deep(a) { color: var(--accent); }
.query-result :deep(blockquote) { border-left: 2.5px solid var(--accent); padding-left: 14px; color: var(--text-secondary); margin: 10px 0; }
</style>
