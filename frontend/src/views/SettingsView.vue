<script setup lang="ts">
/**
 * 项目设置——LLM 配置 + 备份恢复 + 审计日志。
 */
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { projectsApi } from '@/api/projects'
import { maintenanceApi } from '@/api/maintenance'

const route = useRoute()
const projectId = route.params.projectId as string

const settings = ref<any>(null)
const loading = ref(false)
const saved = ref(false)
const auditLog = ref<any[]>([])
const auditLoading = ref(true)
const auditError = ref('')
const showImport = ref(false)

async function loadSettings() {
  loading.value = true
  try { const res = await projectsApi.getSettings(projectId); settings.value = res.data?.settings || { llm: {}, features: {} } }
  catch (e) { console.error(e) } finally { loading.value = false }
}

async function saveSettings() {
  loading.value = true
  try { await projectsApi.updateSettings(projectId, settings.value); saved.value = true; setTimeout(() => saved.value = false, 2000) }
  catch (e) { console.error(e) } finally { loading.value = false }
}

async function loadAuditLog() {
  auditLoading.value = true
  auditError.value = ''
  // 兜底：5 秒后无论如何结束 loading 状态
  const fallback = setTimeout(() => {
    if (auditLoading.value) {
      auditLoading.value = false
      auditError.value = '请求超时'
    }
  }, 5000)
  try {
    const res = await maintenanceApi.getAuditLog(projectId, 50)
    auditLog.value = res.data?.entries || []
  } catch (e: any) {
    if (e?.code !== 'ERR_CANCELED') {
      auditError.value = e.response?.status === 403 ? '无权限查看操作记录' : '加载失败'
    }
  } finally {
    clearTimeout(fallback)
    auditLoading.value = false
  }
}

async function handleExport() {
  try {
    const res = await maintenanceApi.exportBackup(projectId)
    const url = window.URL.createObjectURL(new Blob([res.data]))
    const a = document.createElement('a'); a.href = url; a.download = `backup-${projectId}-${Date.now()}.tar.gz`; a.click()
    window.URL.revokeObjectURL(url)
  } catch (e) { console.error(e) }
}

onMounted(() => { loadSettings(); loadAuditLog() })
</script>

<template>
  <div class="settings-page">
    <h2>项目设置</h2>

    <!-- LLM 配置 -->
    <div class="card" style="margin-bottom:18px" v-if="settings">
      <h3 class="card-title">LLM 参数</h3>
      <p class="card-desc">为该知识库覆盖全局 LLM 配置。留空则使用系统默认值。</p>
      <div class="fields-row">
        <div class="field">
          <label>模型</label>
          <input v-model="settings.llm.model" placeholder="deepseek/deepseek-v4-flash" />
        </div>
        <div class="field">
          <label>API 地址</label>
          <input v-model="settings.llm.api_base" placeholder="http://..." />
        </div>
        <div class="field field-sm">
          <label>Temperature</label>
          <input v-model.number="settings.llm.temperature" type="number" step="0.1" min="0" max="2" placeholder="0.3" />
        </div>
        <div class="field field-sm">
          <label>Max Tokens</label>
          <input v-model.number="settings.llm.max_tokens" type="number" step="100" placeholder="8192" />
        </div>
      </div>
    </div>

    <!-- 功能开关 -->
    <div class="card" style="margin-bottom:18px" v-if="settings">
      <h3 class="card-title">功能</h3>
      <div class="toggle-list">
        <label class="toggle-row">
          <div class="toggle-switch">
            <input type="checkbox" v-model="settings.features.auto_ingest_on_upload" />
            <span class="toggle-track" />
          </div>
          <div>
            <div class="toggle-title">上传后自动摄入</div>
            <div class="toggle-desc">文件上传完成后立即触发 LLM 知识提取</div>
          </div>
        </label>
        <label class="toggle-row">
          <div class="toggle-switch">
            <input type="checkbox" v-model="settings.features.auto_graph_rebuild" />
            <span class="toggle-track" />
          </div>
          <div>
            <div class="toggle-title">摄入后自动重建图谱</div>
            <div class="toggle-desc">摄入完成后自动重新计算知识图谱</div>
          </div>
        </label>
      </div>
    </div>

    <!-- 备份 -->
    <div class="card" style="margin-bottom:18px">
      <h3 class="card-title">备份与恢复</h3>
      <p class="card-desc">导出项目数据（Wiki 页面 + 源文件 + 图谱）为 tar.gz 压缩包。恢复将覆盖当前数据。</p>
      <div class="backup-actions">
        <button class="btn-primary" @click="handleExport">
          <svg viewBox="0 0 20 20" fill="currentColor" width="16"><path d="M10 2v12M6 10l4 4 4-4M4 16v1a1 1 0 001 1h10a1 1 0 001-1v-1" stroke="currentColor" stroke-width="1.5" fill="none"/></svg>
          导出备份
        </button>
        <button class="btn-secondary" @click="showImport = !showImport">
          <svg viewBox="0 0 20 20" fill="currentColor" width="16"><path d="M10 14V2M6 6l4-4 4 4M4 16v1a1 1 0 001 1h10a1 1 0 001-1v-1" stroke="currentColor" stroke-width="1.5" fill="none"/></svg>
          导入备份
        </button>
      </div>
    </div>

    <!-- 审计日志 -->
    <div class="card">
      <h3 class="card-title">操作记录</h3>
      <div v-if="auditLoading" style="color:var(--text-muted);font-size:13px;padding:12px 0">加载中...</div>
      <div v-else-if="auditError" style="color:var(--error-text);font-size:13px;padding:12px 0">
        {{ auditError }}
        <button class="btn-ghost" style="font-size:12px;margin-left:8px;padding:2px 8px" @click="loadAuditLog()">重试</button>
      </div>
      <div v-else-if="auditLog.length === 0" style="color:var(--text-muted);font-size:13px;padding:12px 0">暂无操作记录</div>
      <table v-else>
        <thead><tr><th>时间</th><th>操作</th><th>用户</th><th>目标</th></tr></thead>
        <tbody>
          <tr v-for="log in auditLog.slice(0, 30)" :key="log.id">
            <td class="time-col">{{ (log.timestamp || '').slice(0, 16).replace('T', ' ') }}</td>
            <td><span class="badge badge-muted">{{ log.action }}</span></td>
            <td>{{ log.username }}</td>
            <td class="target-col">{{ log.target }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 保存 -->
    <div class="save-bar">
      <button class="btn-primary" :disabled="loading" @click="saveSettings">
        <template v-if="saved">&#10003; 已保存</template>
        <template v-else>保存设置</template>
      </button>
    </div>
  </div>
</template>

<style scoped>
.settings-page { width: 100%; padding-bottom: 40px; }

h2 { font-size: 22px; font-weight: 700; letter-spacing: -0.4px; margin-bottom: 22px; }

.card-title { font-size: 15px; font-weight: 650; margin-bottom: 4px; }
.card-desc { font-size: 13px; color: var(--text-muted); margin-bottom: 16px; }

.fields-row { display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 12px; }
.field { display: flex; flex-direction: column; }
.field label { font-size: 11px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.4px; margin-bottom: 4px; }
.field input { font-size: 13px; padding: 9px 12px; }
.field-sm { max-width: 120px; }

.toggle-list { display: flex; flex-direction: column; gap: 0; }
.toggle-row {
  display: flex; align-items: flex-start; gap: 14px; padding: 12px 0;
  border-bottom: 1px solid var(--border-light); cursor: pointer;
}
.toggle-row:last-child { border-bottom: none; }

.toggle-switch { position: relative; width: 40px; height: 22px; flex-shrink: 0; }
.toggle-switch input { position: absolute; opacity: 0; width: 100%; height: 100%; cursor: pointer; z-index: 1; }
.toggle-track {
  display: block; width: 100%; height: 100%; border-radius: 100px; background: var(--border-strong);
  transition: background var(--transition); position: relative;
}
.toggle-track::after {
  content: ''; position: absolute; top: 2px; left: 2px; width: 18px; height: 18px;
  border-radius: 50%; background: #fff; transition: transform var(--transition); box-shadow: 0 1px 3px rgba(0,0,0,0.15);
}
.toggle-switch input:checked + .toggle-track { background: var(--accent); }
.toggle-switch input:checked + .toggle-track::after { transform: translateX(18px); }

.toggle-title { font-size: 14px; font-weight: 500; }
.toggle-desc { font-size: 12px; color: var(--text-muted); margin-top: 1px; }

.backup-actions { display: flex; gap: 10px; }

table { font-size: 13px; }
.time-col { color: var(--text-muted); font-size: 12px; white-space: nowrap; }
.target-col { color: var(--text-secondary); font-size: 12px; max-width: 240px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.save-bar { margin-top: 24px; }
</style>
