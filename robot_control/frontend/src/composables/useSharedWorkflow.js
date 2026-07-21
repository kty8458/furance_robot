import { reactive } from 'vue'

// 全局共享状态: 当前选中的工作流名 + 执行状态
const state = reactive({
  currentWorkflowName: '',  // '' = 未选中, 显示全局示教点
  execActive: false,        // 是否正在执行
  execLoop: false,          // 是否循环执行
})

export function useSharedWorkflowState() {
  function setWorkflow(name) {
    state.currentWorkflowName = name || ''
  }
  function setExecState(active, loop = false) {
    state.execActive = active
    state.execLoop = loop
  }
  return { state, setWorkflow, setExecState }
}
