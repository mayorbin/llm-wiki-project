<script setup lang="ts">
/**
 * 知识图谱——AntV G6 v5 渲染 + 筛选面板 + 统计。
 */
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { graphApi } from '@/api/graph'
import { Graph } from '@antv/g6'

const route = useRoute()
const projectId = route.params.projectId as string

const loading = ref(false)
const error = ref('')
const stats = ref({ node_count: 0, edge_count: 0, community_count: 0, extracted_edges: 0, inferred_edges: 0 })
let cachedGraphData: any = null
let graphInstance: Graph | null = null

const showSource = ref(true)
const showEntity = ref(true)
const showConcept = ref(true)
const showExtracted = ref(true)
const showInferred = ref(true)

async function loadGraph() {
  loading.value = true; error.value = ''
  try {
    const res = await graphApi.getData(projectId)
    cachedGraphData = res.data
    stats.value = res.data.stats || { node_count: res.data.nodes?.length || 0, edge_count: res.data.edges?.length || 0, community_count: 0, extracted_edges: 0, inferred_edges: 0 }
    loading.value = false
    await nextTick()
    renderGraph(res.data)
  } catch (e: any) {
    error.value = '图谱加载失败'
    loading.value = false
  } finally { /* loading 已在 try/catch 中处理 */ }
}

function renderGraph(data: any) {
  if (graphInstance) { graphInstance.destroy(); graphInstance = null }
  const container = document.getElementById('graph-canvas')
  if (!container || !data.nodes?.length) return

  const hiddenTypes: string[] = []
  if (!showSource.value) hiddenTypes.push('source')
  if (!showEntity.value) hiddenTypes.push('entity')
  if (!showConcept.value) hiddenTypes.push('concept')
  const visibleNodes = data.nodes.filter((n: any) => !hiddenTypes.includes(n.type))
  const ids = new Set(visibleNodes.map((n: any) => n.id))
  const hiddenEdges: string[] = []
  if (!showExtracted.value) hiddenEdges.push('EXTRACTED')
  if (!showInferred.value) hiddenEdges.push('INFERRED')
  const visibleEdges = data.edges.filter((e: any) => !hiddenEdges.includes(e.type) && ids.has(e.source) && ids.has(e.target))

  graphInstance = new Graph({
    container: 'graph-canvas',
    width: container.clientWidth, height: container.clientHeight || 520,
    data: {
      nodes: visibleNodes.map((n: any) => ({
        id: n.id, data: { label: n.label || n.id, nodeType: n.type, community: n.community },
        style: { fill: n.communityColor || n.color || '#9E9E9E' },
      })),
      edges: visibleEdges.map((e: any) => ({
        source: e.source, target: e.target, data: { edgeType: e.type },
        style: { stroke: e.type === 'INFERRED' ? '#FF5722' : '#94A3B8', lineWidth: e.type === 'INFERRED' ? 1.5 : 0.8, lineDash: e.type === 'INFERRED' ? [6, 4] : undefined },
      })),
    },
    layout: { type: 'force', preventOverlap: true, nodeStrength: -200, linkDistance: 120 },
    behaviors: ['drag-canvas', 'zoom-canvas', 'drag-element'],
    autoFit: 'view',
  })
  graphInstance.render()
}

async function handleBuild() {
  try { await graphApi.build(projectId); loadGraph() } catch (e) { console.error(e) }
}

onMounted(() => nextTick(loadGraph))
onUnmounted(() => graphInstance?.destroy())
watch([showSource, showEntity, showConcept, showExtracted, showInferred], () => { if (cachedGraphData) renderGraph(cachedGraphData) })
</script>

<template>
  <div class="graph-page">
    <!-- 头部 -->
    <div class="graph-header">
      <div>
        <h2>知识图谱</h2>
        <p class="graph-desc" v-if="stats.node_count">共 {{ stats.node_count }} 个节点，{{ stats.edge_count }} 条边</p>
      </div>
      <div class="header-actions">
        <div class="stat-pills">
          <span class="stat-pill extracted">显式 {{ stats.extracted_edges || 0 }}</span>
          <span class="stat-pill inferred">推断 {{ stats.inferred_edges || 0 }}</span>
        </div>
        <button class="btn-primary btn-sm" @click="handleBuild">重建图谱</button>
      </div>
    </div>

    <div class="graph-body">
      <!-- 筛选面板 -->
      <div class="filter-bar">
        <div class="filter-group">
          <span class="filter-label">节点</span>
          <button :class="{ on: showSource }" @click="showSource = !showSource"><span class="dot source" />源文件</button>
          <button :class="{ on: showEntity }" @click="showEntity = !showEntity"><span class="dot entity" />实体</button>
          <button :class="{ on: showConcept }" @click="showConcept = !showConcept"><span class="dot concept" />概念</button>
        </div>
        <div class="filter-divider" />
        <div class="filter-group">
          <span class="filter-label">边</span>
          <button :class="{ on: showExtracted }" @click="showExtracted = !showExtracted"><span class="edge-line solid" />显式</button>
          <button :class="{ on: showInferred }" @click="showInferred = !showInferred"><span class="edge-line dash" />推断</button>
        </div>
      </div>

      <!-- 画布 -->
      <div class="canvas-wrap">
        <div v-if="stats.node_count === 0 && !loading" class="empty-state">
          <svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="1.2" opacity="0.2">
            <circle cx="12" cy="16" r="5"/><circle cx="32" cy="32" r="5"/><circle cx="52" cy="20" r="5"/>
            <line x1="16" y1="18.5" x2="27.5" y2="29"/><line x1="36.5" y1="29" x2="47.5" y2="22.5"/>
          </svg>
          <h3>图谱尚未生成</h3>
          <p>摄入至少 2 个文件后将自动生成知识图谱</p>
          <button class="btn-primary btn-sm" @click="handleBuild">立即构建</button>
        </div>
        <div v-else-if="loading" class="loading-state">加载图谱数据...</div>
        <div v-else id="graph-canvas" class="canvas" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.graph-page { width: 100%; }
.graph-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; }

h2 { font-size: 22px; font-weight: 700; letter-spacing: -0.4px; margin-bottom: 2px; }
.graph-desc { font-size: 13px; color: var(--text-muted); }

.header-actions { display: flex; align-items: center; gap: 12px; }
.stat-pills { display: flex; gap: 6px; }
.stat-pill { font-size: 11px; font-weight: 600; padding: 3px 10px; border-radius: 100px; }
.stat-pill.extracted { background: #F1F5F9; color: #475569; }
.stat-pill.inferred { background: #FFF7ED; color: var(--accent); }

.btn-sm { padding: 7px 16px; font-size: 13px; }

.graph-body { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius-lg); box-shadow: var(--shadow-xs); overflow: hidden; }

.filter-bar { display: flex; align-items: center; gap: 0; padding: 10px 16px; border-bottom: 1px solid var(--border-light); background: var(--bg-subtle); }
.filter-group { display: flex; align-items: center; gap: 4px; }
.filter-label { font-size: 11px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; margin-right: 6px; }
.filter-group button { padding: 5px 10px; border-radius: 100px; font-size: 12px; background: transparent; color: var(--text-muted); display: flex; align-items: center; gap: 6px; font-weight: 500; }
.filter-group button:hover { background: var(--bg-card); color: var(--text-secondary); }
.filter-group button.on { background: var(--bg-card); color: var(--text-primary); font-weight: 600; box-shadow: var(--shadow-xs); }
.dot { width: 8px; height: 8px; border-radius: 50%; }
.dot.source { background: #4CAF50; } .dot.entity { background: #2196F3; } .dot.concept { background: #FF9800; }
.edge-line { width: 14px; height: 2px; border-radius: 1px; }
.edge-line.solid { background: #94A3B8; } .edge-line.dash { background: repeating-linear-gradient(90deg, #FF5722 0px, #FF5722 3px, transparent 3px, transparent 5px); }
.filter-divider { width: 1px; height: 20px; background: var(--border); margin: 0 12px; }

.canvas-wrap { position: relative; min-height: 460px; }
.canvas { width: 100%; height: 500px; }
.loading-state { display: flex; align-items: center; justify-content: center; height: 400px; color: var(--text-muted); font-size: 14px; }
</style>
