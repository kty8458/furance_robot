import api from '.'

export const taskApi = {
  listTemplates: () => api.get('/dispatch/tasks/templates'),
  executeTask: (templateId, robotId) => api.post('/dispatch/tasks/execute', { template_id: templateId, robot_id: robotId }),
  listExecutions: () => api.get('/dispatch/tasks/executions'),
  getExecution: (id) => api.get(`/dispatch/tasks/executions/${id}`),
  cancelExecution: (id) => api.post(`/dispatch/tasks/executions/${id}/cancel`),
}