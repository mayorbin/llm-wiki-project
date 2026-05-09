// frontend/src/api/graph.ts
import client from './client'

export const graphApi = {
  getGraph(projectId: string) {
    return client.get('/graph', { params: { project_id: projectId } })
  },
  getNodeDetail(projectId: string, nodeId: string) {
    return client.get(`/graph/nodes/${nodeId}`, { params: { project_id: projectId } })
  },
  getSubgraph(projectId: string, nodeIds: string[], depth = 1) {
    return client.post('/graph/subgraph', { project_id: projectId, node_ids: nodeIds, depth })
  },
  rebuildGraph(projectId: string) {
    return client.post('/graph/rebuild', { project_id: projectId })
  },
}
