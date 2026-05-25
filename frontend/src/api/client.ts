// frontend/src/api/client.ts
import axios, { type AxiosInstance, type AxiosError, type InternalAxiosRequestConfig } from 'axios'
import { ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import router from '@/router'

// 全局活跃请求计数器（用于顶部加载条）
export const activeRequests = ref(0)

// 请求取消 Map
export const pendingRequests = new Map<string, AbortController>()

const client: AxiosInstance = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

// 请求拦截器——自动注入 JWT
client.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const auth = useAuthStore()
  if (auth.accessToken) {
    config.headers.Authorization = `Bearer ${auth.accessToken}`
  }
  activeRequests.value++
  return config
})

let isRefreshing = false

// 响应拦截器——401 自动刷新 Token、统一错误处理
client.interceptors.response.use(
  (response) => {
    activeRequests.value--
    return response
  },
  async (error: AxiosError) => {
    activeRequests.value--
    const url = error.config?.url || ''
    // 跳过 auth 相关端点，避免 /auth/refresh 自身 401 触发无限刷新
    const isAuthEndpoint = url.includes('/auth/')
    if (error.response?.status === 401 && !isAuthEndpoint) {
      if (isRefreshing) return Promise.reject(error)
      isRefreshing = true
      const auth = useAuthStore()
      try {
        await auth.refreshToken()
        isRefreshing = false
        return client.request(error.config!)
      } catch {
        isRefreshing = false
        auth.logout()
        router.push('/login')
      }
    }
    return Promise.reject(error)
  },
)

export default client
