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
    error.value = e.response?.data?.detail || '登录失败，请检查用户名和密码'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <form class="login-form" @submit.prevent="handleLogin">
      <div class="login-brand">🧠</div>
      <h1>LLM Wiki</h1>
      <p class="subtitle">知识从不丢失</p>

      <div v-if="error" class="error-msg">{{ error }}</div>

      <input v-model="username" placeholder="用户名" required autofocus />
      <input v-model="password" type="password" placeholder="密码" required />
      <button type="submit" class="login-btn" :disabled="loading">
        {{ loading ? '登录中...' : '登录' }}
      </button>
    </form>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-page);
}

.login-form {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  padding: 48px 40px;
  width: 380px;
  text-align: center;
  box-shadow: 0 2px 8px rgba(0,0,0,0.04);
}

.login-brand { font-size: 48px; margin-bottom: 8px; }

h1 { font-size: 22px; color: var(--text-primary); font-weight: 600; }

.subtitle { font-size: 13px; color: var(--text-secondary); margin-bottom: 24px; }

input {
  width: 100%;
  padding: 10px 14px;
  margin-bottom: 12px;
}

.login-btn {
  width: 100%;
  padding: 10px;
  background: var(--accent);
  color: #fff;
  font-weight: 500;
  margin-top: 4px;
}

.login-btn:disabled { opacity: 0.6; }

.error-msg {
  background: var(--error-bg);
  color: var(--error-text);
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  margin-bottom: 12px;
}
</style>
