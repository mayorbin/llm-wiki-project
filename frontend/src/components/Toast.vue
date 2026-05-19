<script setup lang="ts">
/**
 * Toast 通知组件——顶部居中弹出，自动消失。
 * 在 App.vue 中全局挂载一次即可。
 */
import { useToast } from '@/composables/useToast'

const { messages, remove } = useToast()

const iconMap: Record<string, string> = {
  error: 'M8.5 5.5l7 7M15.5 5.5l-7 7',
  success: 'M5 10l3 3 6-6',
  warning: 'M10 3v8M10 15v1',
  info: 'M10 7v4M10 12v1',
}
</script>

<template>
  <Teleport to="body">
    <div class="toast-container" v-if="messages.length > 0">
      <TransitionGroup name="toast">
        <div
          v-for="m in messages"
          :key="m.id"
          class="toast-item"
          :class="`toast-${m.type}`"
          @click="remove(m.id)"
        >
          <svg class="toast-icon" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" width="16">
            <path :d="iconMap[m.type] || iconMap.info"/>
          </svg>
          <span class="toast-text">{{ m.text }}</span>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<style scoped>
.toast-container {
  position: fixed; top: 16px; left: 50%; transform: translateX(-50%);
  z-index: 10000; display: flex; flex-direction: column; gap: 8px;
  pointer-events: none;
}
.toast-item {
  display: flex; align-items: center; gap: 9px;
  padding: 11px 18px; border-radius: var(--radius);
  font-size: 14px; font-weight: 500; line-height: 1.4;
  box-shadow: var(--shadow-lg);
  cursor: pointer; pointer-events: auto;
  max-width: 440px;
}
.toast-icon { flex-shrink: 0; }

.toast-error   { background: var(--error-bg);   color: var(--error-text);   }
.toast-success { background: var(--success-bg); color: var(--success-text); }
.toast-warning { background: var(--warning-bg); color: var(--warning-text); }
.toast-info    { background: var(--bg-card);    color: var(--text-primary); border: 1px solid var(--border); }

.toast-enter-active { transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1); }
.toast-leave-active { transition: all 0.2s ease-in; }
.toast-enter-from   { opacity: 0; transform: translateY(-10px) scale(0.96); }
.toast-leave-to      { opacity: 0; transform: translateY(-6px) scale(0.96); }
</style>
