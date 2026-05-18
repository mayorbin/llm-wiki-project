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
  loading.value = true
  error.value = ''
  try {
    await auth.login(username.value, password.value)
    const redirect = (route.query.redirect as string) || '/'
    router.push(redirect)
  } catch (e: any) {
    error.value = e.response?.data?.detail || '用户名或密码错误'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-card">
      <svg class="logo" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect width="48" height="48" rx="12" fill="url(#login-grad)"/>
        <path d="M15 17h18v2H15zM15 22.5h13v2H15zM15 28h15v2H15z" fill="#fff"/>
        <circle cx="33" cy="18" r="2" fill="rgba(255,255,255,0.5)"/>
        <circle cx="36" cy="18" r="2" fill="rgba(255,255,255,0.5)"/>
        <circle cx="33" cy="23.5" r="2" fill="rgba(255,255,255,0.5)"/>
        <circle cx="36" cy="23.5" r="2" fill="rgba(255,255,255,0.5)"/>
        <circle cx="33" cy="29" r="2" fill="rgba(255,255,255,0.5)"/>
        <circle cx="36" cy="29" r="2" fill="rgba(255,255,255,0.5)"/>
        <defs>
          <linearGradient id="login-grad" x1="0" y1="0" x2="48" y2="48">
            <stop stop-color="#D97706"/><stop offset="1" stop-color="#EA580C"/>
          </linearGradient>
        </defs>
      </svg>

      <h1>LLM Wiki</h1>
      <p class="sub">知识从不丢失</p>

      <div v-if="error" class="error-msg">{{ error }}</div>

      <form @submit.prevent="handleLogin">
        <input v-model="username" placeholder="用户名" autofocus :disabled="loading" />
        <input v-model="password" type="password" placeholder="密码" :disabled="loading" />
        <button type="submit" class="btn-primary login-btn" :disabled="loading">
          {{ loading ? '登录中...' : '登录' }}
        </button>
      </form>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background:
    radial-gradient(ellipse 80% 50% at 50% -20%, rgba(217,119,6,0.06), transparent),
    radial-gradient(ellipse 50% 80% at 80% 120%, rgba(217,119,6,0.04), transparent),
    var(--bg-page);
}

.login-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 48px 44px;
  width: 400px;
  text-align: center;
  box-shadow: var(--shadow-lg);
}

.logo { width: 48px; height: 48px; margin-bottom: 16px; }

h1 { font-size: 24px; margin-bottom: 4px; }

.sub { font-size: 14px; color: var(--text-muted); margin-bottom: 28px; }

form input {
  margin-bottom: 12px;
  padding: 12px 16px;
}

.login-btn {
  width: 100%;
  padding: 12px;
  margin-top: 4px;
}

.login-btn:disabled { opacity: 0.6; cursor: not-allowed; transform: none; }

.error-msg {
  background: var(--error-bg);
  color: var(--error-text);
  padding: 10px 14px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  margin-bottom: 16px;
  text-align: left;
}
</style>
