<script setup lang="ts">
/**
 * 知识图谱——AntV G6 v5 渲染 + 筛选面板。
 */
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { graphApi } from '@/api/graph'
import { Graph } from '@antv/g6'

const route = useRoute()
const projectId = route.params.projectId as string

const loading = ref(false)
const error = ref('')
const stats = ref({ node_count: 0, edge_count: 0, community_count: 0 })

// 缓存原始图谱数据，用于筛选时重新渲染（避免重复请求）
let cachedGraphData: any = null
let graphInstance: Graph | null = null

// 筛选状态
const showSource = ref(true)
const showEntity = ref(true)
const showConcept = ref(true)
const showExtracted = ref(true)
const showInferred = ref(true)

async function loadGraph() {
  loading.value = true
  error.value = ''
  try {
    const res = await graphApi.getData(projectId)
    const data = res.data
    cachedGraphData = data
    renderGraph(data)
    stats.value = data.stats || {
      node_count: data.nodes?.length || 0,
      edge_count: data.edges?.length || 0,
      community_count: 0,
    }
  } catch (e: any) {
    error.value = '图谱加载失败'
    console.error('加载图谱失败:', e)
  } finally {
    loading.value = false
  }
}

function renderGraph(data: any) {
  // 销毁旧实例
  if (graphInstance) { graphInstance.destroy(); graphInstance = null }

  const container = document.getElementById('graph-container')
  if (!container || !data.nodes?.length) return

  // 筛选节点类型
  const hiddenNodeTypes: string[] = []
  if (!showSource.value) hiddenNodeTypes.push('source')
  if (!showEntity.value) hiddenNodeTypes.push('entity')
  if (!showConcept.value) hiddenNodeTypes.push('concept')

  const visibleNodes = data.nodes.filter((n: any) => !hiddenNodeTypes.includes(n.type))
  const visibleNodeIds = new Set(visibleNodes.map((n: any) => n.id))

  // 筛选边类型
  const hiddenEdgeTypes: string[] = []
  if (!showExtracted.value) hiddenEdgeTypes.push('EXTRACTED')
  if (!showInferred.value) hiddenEdgeTypes.push('INFERRED')

  const visibleEdges = data.edges.filter(
    (e: any) => !hiddenEdgeTypes.includes(e.type) && visibleNodeIds.has(e.source) && visibleNodeIds.has(e.target)
  )

  // 构建 G6 数据
  const g6Data = {
    nodes: visibleNodes.map((n: any) => ({
      id: n.id,
      data: {
        label: n.label || n.id,
        nodeType: n.type,
        community: n.community,
      },
      style: {
        fill: n.communityColor || n.color || '#9E9E9E',
      },
    })),
    edges: visibleEdges.map((e: any) => ({
      source: e.source,
      target: e.target,
      data: { edgeType: e.type },
      style: {
        stroke: e.type === 'INFERRED' ? '#FF5722' : '#555555',
        lineWidth: e.type === 'INFERRED' ? 1.5 : 1,
        lineDash: e.type === 'INFERRED' ? [5, 5] : undefined,
      },
    })),
  }

  graphInstance = new Graph({
    container: 'graph-container',
    width: container.clientWidth,
    height: container.clientHeight || 500,
    data: g6Data,
    layout: { type: 'force', preventOverlap: true, nodeStrength: -200 },
    behaviors: ['drag-canvas', 'zoom-canvas', 'drag-element'],
    autoFit: 'view',
  })

  graphInstance.render()
}

/** 切换筛选时仅重新渲染，不重新请求后端 */
function applyFilter() {
  if (cachedGraphData) {
    renderGraph(cachedGraphData)
  }
}

async function handleBuild() {
  try {
    await graphApi.build(projectId)
    await loadGraph()
  } catch (e) {
    console.error('重建图谱失败:', e)
  }
}

onMounted(() => { nextTick(loadGraph) })
onUnmounted(() => { graphInstance?.destroy() })
watch([showSource, showEntity, showConcept, showExtracted, showInferred], applyFilter)
</script>

<template>
  <div class="graph-page">
    <div class="graph-header">
      <h2>知识图谱</h2>
      <div class="graph-actions">
        <span class="stat">节点 {{ stats.node_count }}</span>
        <span class="stat">边 {{ stats.edge_count }}</span>
        <button @click="handleBuild" class="build-btn">重建图谱</button>
      </div>
    </div>

    <div class="graph-layout">
      <div class="filter-panel">
        <div class="filter-section">
          <div class="filter-title">节点类型</div>
          <label><input type="checkbox" v-model="showSource" /> 🟢 源文件</label>
          <label><input type="checkbox" v-model="showEntity" /> 🔵 实体</label>
          <label><input type="checkbox" v-model="showConcept" /> 🟠 概念</label>
        </div>
        <div class="filter-section">
          <div class="filter-title">边类型</div>
          <label><input type="checkbox" v-model="showExtracted" /> 显式链接</label>
          <label><input type="checkbox" v-model="showInferred" /> LLM 推断</label>
        </div>
      </div>

      <div class="graph-canvas">
        <div v-if="stats.node_count === 0 && !loading" class="empty-state">
          <div class="empty-icon">🔗</div>
          <p>图谱未生成</p>
          <p class="empty-hint">摄入至少 2 个文件后自动生成</p>
          <button @click="handleBuild" class="build-btn">立即构建</button>
        </div>
        <div v-else-if="loading" class="loading">加载中...</div>
        <div v-else-if="error" class="error">{{ error }}</div>
        <div v-else id="graph-container" class="graph-container"></div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.graph-page { max-width: 1200px; }

.graph-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

h2 { font-size: 20px; font-weight: 600; }

.graph-actions { display: flex; align-items: center; gap: 16px; }

.stat { font-size: 12px; color: var(--text-secondary); }

.build-btn {
  padding: 8px 16px;
  background: var(--accent);
  color: #fff;
  font-size: 13px;
}

.graph-layout { display: flex; gap: 16px; height: 500px; }

.filter-panel {
  width: 180px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
  padding: 16px;
  flex-shrink: 0;
}

.filter-section { margin-bottom: 16px; }

.filter-title {
  font-weight: 600;
  font-size: 11px;
  color: var(--text-secondary);
  text-transform: uppercase;
  margin-bottom: 6px;
}

.filter-section label {
  display: block;
  font-size: 12px;
  padding: 3px 0;
  cursor: pointer;
}

.filter-section input { margin-right: 6px; accent-color: var(--accent); }

.graph-canvas {
  flex: 1;
  background: #1a1a2e;
  border-radius: var(--radius);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  min-height: 400px;
}

.graph-container { width: 100%; height: 100%; }

.empty-state { text-align: center; color: #e2e8f0; }

.empty-icon { font-size: 48px; margin-bottom: 12px; }

.empty-hint { font-size: 12px; color: #94a3b8; margin: 4px 0 16px; }

.loading { color: #e2e8f0; }
</style>
