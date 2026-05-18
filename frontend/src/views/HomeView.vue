<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { projectsApi } from '@/api/projects'

const router = useRouter()
const auth = useAuthStore()
const projectName = ref('')
const projectDesc = ref('')
const creating = ref(false)
const error = ref('')
const projects = computed(() => auth.projects || [])

function goToProject(id: string) { router.push(`/${id}`) }

async function createProject() {
  if (!projectName.value.trim()) return
  creating.value = true; error.value = ''
  try {
    const res = await projectsApi.create(projectName.value.trim(), projectDesc.value.trim())
    await auth.initialize()
    router.push(`/${res.data.id || res.data.project_id}`)
  } catch (e: any) { error.value = e.response?.data?.detail || '创建失败' }
  finally { creating.value = false }
}

const features = [
  { icon: 'upload', title: '上传文件', desc: '支持 PDF / DOCX / Markdown / 音视频等格式，自动转换' },
  { icon: 'brain', title: 'LLM 摄入', desc: 'AI 自动提取实体、概念和关系，构建知识页面' },
  { icon: 'graph', title: '知识图谱', desc: '自动生成关联图谱，发现隐式连接' },
]
</script>

<template>
  <div class="home-page">
    <div class="home-container">
      <!-- 顶部 -->
      <header class="home-header">
        <svg class="hero-logo" viewBox="0 0 56 56" fill="none" xmlns="http://www.w3.org/2000/svg">
          <rect width="56" height="56" rx="14" fill="url(#home-grad)"/>
          <path d="M17 19h22v2H17zM17 24.5h15v2H17zM17 30h17v2H17z" fill="#fff"/>
          <circle cx="38" cy="20" r="2" fill="rgba(255,255,255,0.45)"/><circle cx="42" cy="20" r="2" fill="rgba(255,255,255,0.45)"/>
          <circle cx="38" cy="25.5" r="2" fill="rgba(255,255,255,0.45)"/><circle cx="42" cy="25.5" r="2" fill="rgba(255,255,255,0.45)"/>
          <circle cx="38" cy="31" r="2" fill="rgba(255,255,255,0.45)"/><circle cx="42" cy="31" r="2" fill="rgba(255,255,255,0.45)"/>
          <defs><linearGradient id="home-grad" x1="0" y1="0" x2="56" y2="56"><stop stop-color="#D97706"/><stop offset="1" stop-color="#EA580C"/></linearGradient></defs>
        </svg>
        <h1>LLM Wiki</h1>
        <p class="slogan">上传文件，AI 自动构建知识库和知识图谱</p>
      </header>

      <!-- 功能介绍 -->
      <div class="features-row">
        <div v-for="f in features" :key="f.icon" class="feature-card">
          <div class="feature-icon-wrap">
            <svg class="feature-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
              <template v-if="f.icon === 'upload'">
                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
              </template>
              <template v-else-if="f.icon === 'brain'">
                <path d="M12 2a7 7 0 00-7 7c0 2.4 1.2 4.5 3 5.7V19l3-2 3 2v-4.3c1.8-1.2 3-3.3 3-5.7a7 7 0 00-7-7z"/>
                <circle cx="9" cy="9" r="1"/><circle cx="15" cy="9" r="1"/>
              </template>
              <template v-else>
                <circle cx="5" cy="19" r="2"/><circle cx="12" cy="8" r="2"/><circle cx="19" cy="14" r="2"/>
                <line x1="6.5" y1="17.5" x2="10.5" y2="9.5"/><line x1="13.5" y1="9.5" x2="17.5" y2="12.5"/>
              </template>
            </svg>
          </div>
          <h4>{{ f.title }}</h4>
          <p>{{ f.desc }}</p>
        </div>
      </div>

      <!-- 项目列表 -->
      <div v-if="projects.length > 0" class="section">
        <h3>你的项目</h3>
        <div class="project-grid">
          <button v-for="p in projects" :key="p.id" class="project-card" @click="goToProject(p.id)">
            <div class="project-card-top">
              <span class="project-initial">{{ p.name[0] }}</span>
              <div>
                <div class="project-card-name">{{ p.name }}</div>
                <div class="project-card-role">{{ p.role === 'owner' ? 'Owner' : p.role === 'editor' ? 'Editor' : 'Viewer' }}</div>
              </div>
            </div>
            <span v-if="p.status === 'archived'" class="badge badge-warning">已归档</span>
            <svg v-else class="chevron" viewBox="0 0 20 20" fill="currentColor" width="18"><path d="M7 4l8 6-8 6" stroke="currentColor" stroke-width="2" fill="none"/></svg>
          </button>
        </div>
      </div>

      <!-- 创建 -->
      <div class="section">
        <h3>创建新项目</h3>
        <div class="create-card">
          <div v-if="error" class="error-msg">{{ error }}</div>
          <div class="create-fields">
            <input v-model="projectName" placeholder="项目名称" :disabled="creating" class="name-input" @keyup.enter="createProject" />
            <input v-model="projectDesc" placeholder="描述（可选）" :disabled="creating" class="desc-input" />
            <button class="btn-primary" :disabled="creating || !projectName.trim()" @click="createProject">
              {{ creating ? '创建中...' : '创建项目' }}
            </button>
          </div>
        </div>
      </div>

      <div class="home-footer">
        <span>{{ auth.user?.username }}</span>
        <button class="btn-ghost" @click="auth.logout(); router.push('/login')">退出登录</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.home-page { min-height: 100vh; display: flex; justify-content: center; background: radial-gradient(ellipse 60% 50% at 50% -10%, rgba(217,119,6,0.04), transparent), var(--bg-page); padding: 48px 24px 80px; }
.home-container { width: 100%; max-width: 720px; }

.home-header { text-align: center; margin-bottom: 44px; }
.hero-logo { width: 56px; height: 56px; margin-bottom: 18px; }
h1 { font-size: 30px; font-weight: 750; letter-spacing: -0.8px; margin-bottom: 8px; }
.slogan { font-size: 15px; color: var(--text-secondary); }

.features-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-bottom: 44px; }
.feature-card {
  background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius-lg);
  padding: 24px 20px; text-align: center; box-shadow: var(--shadow-xs); transition: all var(--transition);
}
.feature-card:hover { box-shadow: var(--shadow); transform: translateY(-2px); }

.feature-icon-wrap { width: 40px; height: 40px; border-radius: var(--radius); background: var(--accent-light); display: flex; align-items: center; justify-content: center; margin: 0 auto 12px; }
.feature-icon { width: 20px; height: 20px; color: var(--accent); }
.feature-card h4 { font-size: 14px; margin-bottom: 4px; }
.feature-card p { font-size: 12.5px; color: var(--text-muted); line-height: 1.55; }

.section { margin-bottom: 32px; }
.section h3 { font-size: 16px; font-weight: 650; margin-bottom: 14px; }

.project-grid { display: flex; flex-direction: column; gap: 6px; }

.project-card {
  display: flex; align-items: center; justify-content: space-between;
  width: 100%; padding: 14px 18px; background: var(--bg-card); border: 1px solid var(--border);
  border-radius: var(--radius); text-align: left; box-shadow: var(--shadow-xs);
  transition: all var(--transition);
}
.project-card:hover { border-color: var(--accent); box-shadow: var(--shadow-sm); transform: translateX(2px); }

.project-card-top { display: flex; align-items: center; gap: 12px; }
.project-initial { width: 36px; height: 36px; border-radius: var(--radius-sm); background: var(--accent-light); color: var(--accent); display: flex; align-items: center; justify-content: center; font-size: 16px; font-weight: 700; }
.project-card-name { font-size: 15px; font-weight: 600; line-height: 1.3; }
.project-card-role { font-size: 12px; color: var(--text-muted); }
.chevron { color: var(--text-muted); flex-shrink: 0; }

.create-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 24px; box-shadow: var(--shadow-xs); }
.create-fields { display: flex; gap: 10px; }
.name-input { flex: 2; }
.desc-input { flex: 3; }
.create-fields .btn-primary { flex-shrink: 0; min-width: 100px; }

.error-msg { background: var(--error-bg); color: var(--error-text); padding: 8px 14px; border-radius: var(--radius); font-size: 13px; margin-bottom: 12px; }

.home-footer { display: flex; justify-content: space-between; align-items: center; padding-top: 20px; border-top: 1px solid var(--border-light); font-size: 12px; color: var(--text-muted); }
</style>
