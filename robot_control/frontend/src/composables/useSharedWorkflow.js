import { reactive } from 'vue'

// 全局共享状态: 当前选中的工作流名
// ArmControl 和 WorkflowEditor 共享
const state = reactive({
  currentWorkflowName: '',  // '' = 未选中, 显示全局示教点
})

export function useSharedWorkflowState() {
  function setWorkflow(name) {
    state.currentWorkflowName = name || ''
  }
  function getWorkflow() {
    return state.currentWorkflowName
  }
  return { state, setWorkflow, getWorkflow }
}
