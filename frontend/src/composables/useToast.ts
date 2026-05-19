// frontend/src/composables/useToast.ts
/** 全局 Toast 消息管理。 */
import { ref } from 'vue'

export interface ToastMessage {
  id: number
  text: string
  type: 'error' | 'success' | 'warning' | 'info'
}

const messages = ref<ToastMessage[]>([])
let _nextId = 0

function push(text: string, type: ToastMessage['type'] = 'info', duration = 5000) {
  const id = ++_nextId
  messages.value.push({ id, text, type })
  if (duration > 0) {
    setTimeout(() => remove(id), duration)
  }
  return id
}

function remove(id: number) {
  const idx = messages.value.findIndex(m => m.id === id)
  if (idx >= 0) messages.value.splice(idx, 1)
}

export function useToast() {
  return {
    messages,
    toast(msg: string) { push(msg, 'info') },
    success(msg: string) { push(msg, 'success') },
    warning(msg: string) { push(msg, 'warning') },
    error(msg: string) { push(msg, 'error') },
    remove,
  }
}
