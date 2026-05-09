<script setup lang="ts">
defineProps<{
  /** 进度百分比 (0-100) */
  progress: number
  /** 步骤名称列表 */
  steps: string[]
  /** 当前步骤索引 (0-based) */
  currentStep: number
}>()
</script>

<template>
  <div class="progress-bar">
    <div class="bar-track">
      <div class="bar-fill" :style="{ width: progress + '%' }" />
    </div>
    <div class="steps">
      <span
        v-for="(step, index) in steps"
        :key="step"
        :class="{
          'step-active': index === currentStep,
          'step-done': index < currentStep,
        }"
      >{{ index > 0 ? '→ ' : '' }}{{ step }}</span>
    </div>
  </div>
</template>

<style scoped>
.progress-bar { margin: 12px 0; }

.bar-track {
  height: 6px;
  background: var(--border-color);
  border-radius: 3px;
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  background: var(--accent);
  border-radius: 3px;
  transition: width 0.3s ease;
}

.steps {
  display: flex;
  gap: 4px;
  margin-top: 8px;
  font-size: 11px;
  color: var(--text-secondary);
  flex-wrap: wrap;
}

.step-active { color: var(--accent); font-weight: 500; }

.step-done { color: var(--success-text); }
</style>
