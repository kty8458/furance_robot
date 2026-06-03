import api from '.'

const ROBOT_ID = 'robot_001'

export const workflowApi = {
  list: () => api.get(`/robot/${ROBOT_ID}/workflows`),
  get: (name) => api.get(`/robot/${ROBOT_ID}/workflows/${name}`),
  save: (name, data) => api.post(`/robot/${ROBOT_ID}/workflows/${name}`, data),
  update: (name, data) => api.put(`/robot/${ROBOT_ID}/workflows/${name}`, data),
  delete: (name) => api.delete(`/robot/${ROBOT_ID}/workflows/${name}`),
  execute: (name, navParams) => api.post(`/robot/${ROBOT_ID}/workflows/${name}/execute`, { nav_params: navParams }),
  getExecution: (executionId) => api.get(`/robot/${ROBOT_ID}/workflows/executions/${executionId}`),
  cancel: (name) => api.post(`/robot/${ROBOT_ID}/workflows/${name}/cancel`),
}
