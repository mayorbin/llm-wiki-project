<script setup lang="ts">
/**
 * 项目设置——LLM 配置 + 备份 + 审计日志。
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

// 审计日志
const auditLog = ref<any[]>([])
const auditLoading = ref(false)

async function loadSettings() {
  loading.value = true
  try {
    const res = await projectsApi.getSettings(projectId)
    // 后端返回 {project_id, settings: {...}, updated_at}，只取 settings 字段
    settings.value = res.data?.settings || { llm: {}, features: {} }
  } catch (e) {
    console.error('加载设置失败:', e)
  } finally {
    loading.value = false
  }
}

async function saveSettings() {
  loading.value = true
  try {
    await projectsApi.updateSettings(projectId, settings.value?.settings || settings.value)
    saved.value = true
    setTimeout(() => saved.value = false, 2000)
  } catch (e) {
    console.error('保存设置失败:', e)
  } finally {
    loading.value = false
  }
}

async function loadAuditLog() {
  auditLoading.value = true
  try {
    const res = await maintenanceApi.getAuditLog(projectId, 50)
    auditLog.value = res.data?.entries || []
  } catch (e) {
    console.error('加载审计日志失败:', e)
  } finally {
    auditLoading.value = false
  }
}

async function handleExport() {
  try {
    const res = await maintenanceApi.exportBackup(projectId)
    const url = window.URL.createObjectURL(new Blob([res.data]))
    const a = document.createElement('a')
    a.href = url
    a.download = `backup-${projectId}-${Date.now()}.tar.gz`
    a.click()
    window.URL.revokeObjectURL(url)
  } catch (e) {
    console.error('导出备份失败:', e)
  }
}

onMounted(() => { loadSettings(); loadAuditLog() })
</script>

<template>
  <div class="settings-page">
    <h2>项目设置</h2>

    <div class="section" v-if="settings">
      <h3>LLM 配置</h3>
      <div class="form-grid">
        <label>模型 <input v-model="settings.llm.model" /></label>
        <label>Temperature <input v-model.number="settings.llm.temperature" type="number" step="0.1" min="0" max="2" /></label>
        <label>Max Tokens <input v-model.number="settings.llm.max_tokens" type="number" /></label>
      </div>
    </div>

    <div class="section" v-if="settings">
      <h3>功能开关</h3>
      <div class="form-grid">
        <label><input type="checkbox" v-model="settings.features.auto_ingest_on_upload" /> 上传后自动摄入</label>
        <label><input type="checkbox" v-model="settings.features.auto_graph_rebuild" /> 摄入后自动重建图谱</label>
      </div>
    </div>

    <div class="section">
      <h3>备份</h3>
      <button @click="handleExport" class="action-btn">📦 导出备份 (tar.gz)</button>
    </div>

    <div class="section">
      <h3>审计日志</h3>
      <div v-if="auditLoading">加载中...</div>
      <table v-else class="audit-table">
        <thead>
          <tr><th>时间</th><th>操作</th><th>用户</th><th>目标</th><th>结果</th></tr>
        </thead>
        <tbody>
          <tr v-for="log in auditLog.slice(0, 20)" :key="log.id">
            <td>{{ log.timestamp?.slice(0, 16) }}</td>
            <td>{{ log.action }}</td>
            <td>{{ log.username }}</td>
            <td>{{ log.target }}</td>
            <td>{{ log.result }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="action-bar">
      <button @click="saveSettings" :disabled="loading" class="save-btn">
        {{ saved ? '已保存' : '保存设置' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.settings-page { max-width: 700px; }

h2 { font-size: 20px; font-weight: 600; margin-bottom: 24px; }

.section {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
  padding: 20px;
  margin-bottom: 16px;
}

h3 { font-size: 15px; font-weight: 600; margin-bottom: 12px; }

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.form-grid label { font-size: 13px; color: var(--text-secondary); }

.form-grid input[type="text"],
.form-grid input[type="number"] {
  display: block;
  width: 100%;
  margin-top: 4px;
}

.form-grid input[type="checkbox"] { margin-right: 6px; accent-color: var(--accent); }

.action-btn {
  padding: 8px 16px;
  background: var(--bg-page);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  border-radius: var(--radius-sm);
}

.audit-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.audit-table th {
  text-align: left;
  padding: 6px 8px;
  border-bottom: 1px solid var(--border-color);
  color: var(--text-secondary);
  font-size: 11px;
}

.audit-table td { padding: 6px 8px; border-bottom: 1px solid var(--bg-page); }

.action-bar { margin-top: 24px; }

.save-btn {
  padding: 10px 24px;
  background: var(--accent);
  color: #fff;
  font-weight: 500;
}
</style>
