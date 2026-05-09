// frontend/src/stores/auth.ts
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi } from '@/api/auth'

export const useAuthStore = defineStore('auth', () => {
  const accessToken = ref<string | null>(localStorage.getItem('access_token'))
  const _refreshToken = ref<string | null>(localStorage.getItem('refresh_token'))
  const user = ref<Record<string, any> | null>(null)
  const projects = ref<any[]>([])

  const isAuthenticated = computed(() => !!accessToken.value)

  async function initialize() {
    if (!accessToken.value) return
    try {
      const res = await authApi.me()
      user.value = res.data.user
      projects.value = res.data.projects
    } catch {
      logout()
    }
  }

  async function login(username: string, password: string) {
    const res = await authApi.login(username, password)
    accessToken.value = res.data.access_token
    _refreshToken.value = res.data.refresh_token
    localStorage.setItem('access_token', res.data.access_token)
    localStorage.setItem('refresh_token', res.data.refresh_token)
    await initialize()
  }

  async function refreshToken() {
    if (!_refreshToken.value) throw new Error('no refresh token')
    const res = await authApi.refresh(_refreshToken.value)
    accessToken.value = res.data.access_token
    _refreshToken.value = res.data.refresh_token
    localStorage.setItem('access_token', res.data.access_token)
    localStorage.setItem('refresh_token', res.data.refresh_token)
  }

  function logout() {
    if (_refreshToken.value) {
      authApi.logout(_refreshToken.value).catch(() => {})
    }
    accessToken.value = null
    _refreshToken.value = null
    user.value = null
    projects.value = []
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('last_project')
  }

  return { accessToken, refreshToken, user, projects, isAuthenticated, initialize, login, logout }
})
