// frontend/src/stores/project.ts
import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useProjectStore = defineStore('project', () => {
  const projectId = ref<string | null>(null)
  const project = ref<Record<string, any> | null>(null)

  async function setCurrentProject(id: string) {
    if (id === projectId.value) return
    projectId.value = id
    localStorage.setItem('last_project', id)
    // 项目数据由各组件自行加载
  }

  function restoreLastProject(): string | null {
    return localStorage.getItem('last_project')
  }

  return { projectId, project, setCurrentProject, restoreLastProject }
})
