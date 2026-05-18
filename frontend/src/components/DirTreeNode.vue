<script setup lang="ts">
/**
 * 递归目录树节点——用于知识库侧边栏。
 */
import { ref, computed } from 'vue'

const props = defineProps<{
  node: { name: string; path: string; children?: any[] }
  depth: number
  currentDir: string
}>()

const emit = defineEmits<{
  select: [path: string]
}>()

const expanded = ref(props.depth < 2)

const subDirs = computed(() =>
  (props.node.children || []).filter((c: any) => c.type === 'directory')
)

function toggle() { expanded.value = !expanded.value }
function onClick() { emit('select', props.node.path) }
</script>

<template>
  <div
    class="tree-node"
    :class="{ active: currentDir === node.path }"
    :style="{ paddingLeft: (depth * 15 + 11) + 'px' }"
    @click="onClick"
  >
    <span
      v-if="subDirs.length > 0"
      class="tree-chevron"
      :class="{ expanded }"
      @click.stop="toggle"
    >
      <svg viewBox="0 0 20 20" fill="currentColor" width="12"><path d="M7 5l5 5-5 5" stroke="currentColor" stroke-width="2" fill="none"/></svg>
    </span>
    <span v-else class="tree-chevron-spacer" />
    <svg class="tree-icon" viewBox="0 0 20 20" fill="currentColor" width="14"><path d="M2 5a2 2 0 012-2h3.6c.4 0 .8.2 1 .5L10 5h6a2 2 0 012 2v8a2 2 0 01-2 2H4a2 2 0 01-2-2V5z"/></svg>
    <span class="tree-name">{{ node.name }}</span>
  </div>
  <template v-if="expanded && subDirs.length > 0">
    <DirTreeNode
      v-for="child in subDirs"
      :key="child.path"
      :node="child"
      :depth="depth + 1"
      :currentDir="currentDir"
      @select="(path: string) => emit('select', path)"
    />
  </template>
</template>

<style scoped>
.tree-node {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 6px 12px 6px 11px;
  font-size: 13px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--transition);
  user-select: none;
}
.tree-node:hover {
  background: var(--bg-subtle);
  color: var(--text-primary);
}
.tree-node.active {
  background: var(--accent-light);
  color: var(--accent);
  font-weight: 600;
}
.tree-node.active .tree-icon { color: var(--accent); }

.tree-chevron {
  display: flex; align-items: center; justify-content: center;
  width: 16px; height: 16px; flex-shrink: 0;
  color: var(--text-muted); transition: transform var(--transition);
}
.tree-chevron.expanded { transform: rotate(90deg); }

.tree-chevron-spacer { width: 16px; flex-shrink: 0; }

.tree-icon {
  color: var(--text-muted); flex-shrink: 0;
}

.tree-name {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
