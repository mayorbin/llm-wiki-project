<script setup lang="ts">
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const username = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

async function handleLogin() {
  loading.value = true; error.value = ''
  try {
    await auth.login(username.value, password.value)
    router.push((route.query.redirect as string) || '/')
  } catch (e: any) {
    error.value = e.response?.data?.detail || '用户名或密码错误'
  } finally { loading.value = false }
}
</script>

<template>
  <div class="login-page">
    <div class="login-panel">
      <!-- 左侧品牌 -->
      <div class="login-brand">
        <svg class="brand-logo" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
          <rect width="48" height="48" rx="12" fill="url(#login-grad)"/>
          <path d="M14 16h20v2H14zM14 21.5h14v2H14zM14 27h16v2H14z" fill="#fff"/>
          <circle cx="33" cy="17" r="2" fill="rgba(255,255,255,0.45)"/>
          <circle cx="36.5" cy="17" r="2" fill="rgba(255,255,255,0.45)"/>
          <circle cx="33" cy="22.5" r="2" fill="rgba(255,255,255,0.45)"/>
          <circle cx="36.5" cy="22.5" r="2" fill="rgba(255,255,255,0.45)"/>
          <circle cx="33" cy="28" r="2" fill="rgba(255,255,255,0.45)"/>
          <circle cx="36.5" cy="28" r="2" fill="rgba(255,255,255,0.45)"/>
          <defs><linearGradient id="login-grad" x1="0" y1="0" x2="48" y2="48"><stop stop-color="#D97706"/><stop offset="1" stop-color="#EA580C"/></linearGradient></defs>
        </svg>
        <h1>LLM Wiki</h1>
        <p class="tagline">构建团队知识库，<br>让信息自动关联成网。</p>
      </div>

      <!-- 右侧表单 -->
      <div class="login-form">
        <h2>登录</h2>
        <p class="form-sub">输入凭据进入知识库</p>
        <div v-if="error" class="error-msg">{{ error }}</div>
        <form @submit.prevent="handleLogin">
          <label>用户名</label>
          <input v-model="username" placeholder="请输入用户名" autofocus :disabled="loading" />
          <label>密码</label>
          <input v-model="password" type="password" placeholder="请输入密码" :disabled="loading" />
          <button type="submit" class="btn-primary login-btn" :disabled="loading">
            {{ loading ? '验证中...' : '登录' }}
          </button>
        </form>
      </div>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh; display: flex; align-items: center; justify-content: center;
  background: radial-gradient(ellipse 70% 50% at 50% -10%, rgba(217,119,6,0.05), transparent), var(--bg-page);
}

.login-panel {
  display: flex; background: var(--bg-card); border: 1px solid var(--border);
  border-radius: var(--radius-xl); overflow: hidden; box-shadow: var(--shadow-lg); width: 740px;
}

.login-brand {
  flex: 1; background: linear-gradient(135deg, #F8F7F4 0%, #F0EDE8 50%, #FEF3C7 100%);
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 56px 40px; text-align: center;
}
.brand-logo { width: 48px; height: 48px; margin-bottom: 20px; }
.login-brand h1 { font-size: 24px; font-weight: 750; margin-bottom: 8px; }
.tagline { font-size: 14px; color: var(--text-secondary); line-height: 1.7; }

.login-form {
  flex: 1; padding: 56px 44px; display: flex; flex-direction: column; justify-content: center;
}
.login-form h2 { font-size: 22px; margin-bottom: 4px; }
.form-sub { font-size: 13px; color: var(--text-muted); margin-bottom: 24px; }

label { display: block; font-size: 12px; font-weight: 600; color: var(--text-secondary); margin-bottom: 4px; margin-top: 12px; }
label:first-of-type { margin-top: 0; }

input { margin-bottom: 12px; padding: 11px 14px; }

.login-btn { width: 100%; padding: 11px 14px; margin-top: 8px; border-radius: var(--radius); }
.login-btn:disabled { opacity: 0.45; cursor: not-allowed; transform: none; }

.error-msg { background: var(--error-bg); color: var(--error-text); padding: 10px 14px; border-radius: var(--radius); font-size: 13px; margin-bottom: 8px; }
</style>
