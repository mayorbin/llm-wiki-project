<script setup lang="ts">
/**
 * 首页——有项目时跳转第一个，无项目时显示创建引导。
 */
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { projectsApi } from '@/api/projects'

const router = useRouter()
const auth = useAuthStore()

const projectName = ref('')
const projectDesc = ref('')
const creating = ref(false)
const error = ref('')

const projects = auth.projects || []

function goToProject(id: string) {
  router.push(`/${id}`)
}

async function createProject() {
  if (!projectName.value.trim()) return
  creating.value = true
  error.value = ''
  try {
    const res = await projectsApi.create(projectName.value.trim(), projectDesc.value.trim())
    const newProject = res.data
    // 刷新项目列表
    await auth.initialize()
    router.push(`/${newProject.id || newProject.project_id}`)
  } catch (e: any) {
    error.value = e.response?.data?.detail || '创建失败'
  } finally {
    creating.value = false
  }
}
</script>

<template>
  <div class="home-page">
    <div class="home-card">
      <div class="brand">🧠 LLM Wiki</div>
      <p class="subtitle">知识从不丢失</p>

      <!-- 有项目：显示项目列表 -->
      <div v-if="projects.length > 0" class="project-list">
        <h2>你的项目</h2>
        <button
          v-for="p in projects" :key="p.id"
          class="project-item"
          @click="goToProject(p.id)"
        >
          <span class="project-name">{{ p.name }}</span>
          <span class="project-role">{{ p.role === 'owner' ? 'Owner' : p.role === 'editor' ? 'Editor' : 'Viewer' }}</span>
          <span v-if="p.status === 'archived'" class="project-archived">📦 已归档</span>
        </button>
      </div>

      <!-- 无项目：引导创建 -->
      <div v-if="projects.length === 0" class="onboarding">
        <h2>欢迎使用 LLM Wiki</h2>
        <p>你还没有加入任何项目。创建一个项目开始吧。</p>
      </div>

      <!-- 创建新项目 -->
      <div class="create-section">
        <h3>创建新项目</h3>
        <div v-if="error" class="error-msg">{{ error }}</div>
        <input
          v-model="projectName"
          placeholder="项目名称（必填）"
          :disabled="creating"
          @keyup.enter="createProject"
        />
        <input
          v-model="projectDesc"
          placeholder="项目描述（可选）"
          :disabled="creating"
        />
        <button class="create-btn" :disabled="creating || !projectName.trim()" @click="createProject">
          {{ creating ? '创建中...' : '创建项目' }}
        </button>
      </div>

      <div class="logout-link">
        <span>{{ auth.user?.username }}</span>
        <button class="logout-btn" @click="auth.logout(); router.push('/login')">退出</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.home-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-page);
}

.home-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  padding: 48px 40px;
  width: 440px;
  text-align: center;
  box-shadow: 0 2px 8px rgba(0,0,0,0.04);
}

.brand { font-size: 28px; font-weight: 700; color: var(--text-primary); }

.subtitle { font-size: 13px; color: var(--text-secondary); margin: 8px 0 32px; }

.project-list { margin-bottom: 24px; text-align: left; }

.project-list h2 {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 12px;
}

.project-item {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 10px 14px;
  margin-bottom: 6px;
  background: var(--bg-page);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  text-align: left;
  font-size: 14px;
  cursor: pointer;
}

.project-item:hover { border-color: var(--accent); }

.project-name { flex: 1; color: var(--text-primary); }

.project-role { font-size: 11px; color: var(--text-secondary); }

.project-archived { font-size: 11px; color: var(--text-secondary); }

.onboarding h2 {
  font-size: 18px;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.onboarding p {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 24px;
}

.create-section {
  text-align: left;
  border-top: 1px solid var(--border-color);
  padding-top: 20px;
}

.create-section h3 {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 12px;
}

input {
  width: 100%;
  margin-bottom: 8px;
}

.create-btn {
  width: 100%;
  padding: 10px;
  background: var(--accent);
  color: #fff;
  font-weight: 500;
  margin-top: 4px;
}

.create-btn:disabled { opacity: 0.6; }

.error-msg {
  background: var(--error-bg);
  color: var(--error-text);
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  margin-bottom: 8px;
}

.logout-link {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid var(--border-color);
  font-size: 12px;
  color: var(--text-secondary);
}

.logout-btn {
  background: transparent;
  color: var(--text-secondary);
  font-size: 12px;
  padding: 4px 8px;
}
</style>
