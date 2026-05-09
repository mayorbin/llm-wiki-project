// frontend/src/api/auth.ts
import client from './client'

export const authApi = {
  login(username: string, password: string) {
    return client.post('/auth/login', { username, password })
  },
  refresh(refreshToken: string) {
    return client.post('/auth/refresh', { refresh_token: refreshToken })
  },
  register(username: string, password: string, displayName: string) {
    return client.post('/auth/register', { username, password, display_name: displayName })
  },
  me() {
    return client.get('/auth/me')
  },
  logout(refreshToken: string) {
    return client.post('/auth/logout', { refresh_token: refreshToken })
  },
}
