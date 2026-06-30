import api from '.'

const ROBOT_ID = 'robot_001'

export const workflowApi = {
  list: () => api.get(`/robot/${ROBOT_ID}/workflows`),
  get: (name) => api.get(`/robot/${ROBOT_ID}/workflows/${name}`),
  save: (name, data) => api.post(`/robot/${ROBOT_ID}/workflows/${name}`, data),
  update: (name, data) => api.put(`/robot/${ROBOT_ID}/workflows/${name}`, data),
  delete: (name) => api.delete(`/robot/${ROBOT_ID}/workflows/${name}`),
  execute: (name, navParams, manualMode = false) => api.post(`/robot/${ROBOT_ID}/workflows/${name}/execute`, { nav_params: navParams, manual_mode: manualMode }),
  getExecution: (executionId) => api.get(`/robot/${ROBOT_ID}/workflows/executions/${executionId}`),
  cancel: (name) => api.post(`/robot/${ROBOT_ID}/workflows/${name}/cancel`),
  triggerNext: (executionId) => api.post(`/robot/${ROBOT_ID}/workflows/executions/${executionId}/next`),
  updateStep: (executionId, stepId, config) => api.post(`/robot/${ROBOT_ID}/workflows/executions/${executionId}/update-step`, { step_id: stepId, config }),
}
