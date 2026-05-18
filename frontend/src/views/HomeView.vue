<script setup lang="ts">
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

function goToProject(id: string) { router.push(`/${id}`) }

async function createProject() {
  if (!projectName.value.trim()) return
  creating.value = true
  error.value = ''
  try {
    const res = await projectsApi.create(projectName.value.trim(), projectDesc.value.trim())
    const newProject = res.data
    await auth.initialize()
    router.push(`/${newProject.id || newProject.project_id}`)
  } catch (e: any) {
    error.value = e.response?.data?.detail || '创建失败'
  } finally { creating.value = false }
}
</script>

<template>
  <div class="home-page">
    <div class="home-card">
      <svg class="hero-logo" viewBox="0 0 56 56" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect width="56" height="56" rx="14" fill="url(#home-grad)"/>
        <path d="M18 20h20v2H18zM18 26h15v2H18zM18 32h17v2H18z" fill="#fff"/>
        <circle cx="38" cy="21" r="2" fill="rgba(255,255,255,0.45)"/>
        <circle cx="42" cy="21" r="2" fill="rgba(255,255,255,0.45)"/>
        <circle cx="38" cy="27" r="2" fill="rgba(255,255,255,0.45)"/>
        <circle cx="42" cy="27" r="2" fill="rgba(255,255,255,0.45)"/>
        <circle cx="38" cy="33" r="2" fill="rgba(255,255,255,0.45)"/>
        <circle cx="42" cy="33" r="2" fill="rgba(255,255,255,0.45)"/>
        <defs>
          <linearGradient id="home-grad" x1="0" y1="0" x2="56" y2="56">
            <stop stop-color="#D97706"/><stop offset="1" stop-color="#EA580C"/>
          </linearGradient>
        </defs>
      </svg>

      <h1>LLM Wiki</h1>
      <p class="tagline">知识从不丢失</p>

      <!-- 有项目 -->
      <div v-if="projects.length > 0" class="project-list">
        <h3>你的项目</h3>
        <button v-for="p in projects" :key="p.id" class="project-row" @click="goToProject(p.id)">
          <span class="project-dot" />
          <span class="project-name">{{ p.name }}</span>
          <span class="project-badge">{{ p.role === 'owner' ? 'Owner' : p.role === 'editor' ? 'Editor' : 'Viewer' }}</span>
          <span v-if="p.status === 'archived'" class="badge badge-warning" style="margin-left: auto">已归档</span>
        </button>
      </div>

      <!-- 无项目 -->
      <div v-else class="onboard">
        <h3>欢迎使用 LLM Wiki</h3>
        <p>你还没有加入任何项目，创建一个开始吧。</p>
      </div>

      <!-- 创建新区 -->
      <div class="create-block">
        <h4>创建新项目</h4>
        <div v-if="error" class="error-msg">{{ error }}</div>
        <input v-model="projectName" placeholder="项目名称" :disabled="creating" @keyup.enter="createProject" />
        <input v-model="projectDesc" placeholder="描述（可选）" :disabled="creating" />
        <button class="btn-primary create-btn" :disabled="creating || !projectName.trim()" @click="createProject">
          {{ creating ? '创建中...' : '创建' }}
        </button>
      </div>

      <div class="home-footer">
        <span>{{ auth.user?.username }}</span>
        <button class="link-btn" @click="auth.logout(); router.push('/login')">退出</button>
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
  background:
    radial-gradient(ellipse 60% 50% at 50% -20%, rgba(217,119,6,0.05), transparent),
    var(--bg-page);
}

.home-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 44px 40px;
  width: 440px;
  text-align: center;
  box-shadow: var(--shadow-lg);
}

.hero-logo { width: 56px; height: 56px; margin-bottom: 16px; }

h1 { font-size: 26px; margin-bottom: 4px; }
.tagline { font-size: 14px; color: var(--text-muted); margin-bottom: 32px; }

.project-list { text-align: left; margin-bottom: 24px; }
.project-list h3 { font-size: 14px; margin-bottom: 12px; color: var(--text-secondary); }

.project-row {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 10px 14px;
  margin-bottom: 4px;
  background: var(--bg-page);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  font-size: 14px;
  text-align: left;
  transition: all var(--transition);
}
.project-row:hover { border-color: var(--accent); box-shadow: var(--shadow-xs); }

.project-dot {
  width: 8px; height: 8px; border-radius: 50%; background: var(--accent); flex-shrink: 0;
}
.project-name { flex: 1; font-weight: 500; }
.project-badge { font-size: 11px; color: var(--text-muted); }

.onboard { margin-bottom: 24px; }
.onboard h3 { font-size: 18px; margin-bottom: 6px; }
.onboard p { font-size: 14px; color: var(--text-secondary); }

.create-block {
  border-top: 1px solid var(--border-light);
  padding-top: 20px;
  text-align: left;
}
.create-block h4 { font-size: 14px; margin-bottom: 10px; }
.create-block input { margin-bottom: 8px; }

.create-btn { width: 100%; padding: 10px; margin-top: 4px; }

.error-msg {
  background: var(--error-bg); color: var(--error-text);
  padding: 8px 12px; border-radius: var(--radius-sm); font-size: 13px; margin-bottom: 8px;
}

.home-footer {
  display: flex; justify-content: space-between; align-items: center;
  margin-top: 24px; padding-top: 16px; border-top: 1px solid var(--border-light);
  font-size: 12px; color: var(--text-secondary);
}
.link-btn { background: none; color: var(--text-muted); font-size: 12px; padding: 4px; }
.link-btn:hover { color: var(--error-text); }
</style>
