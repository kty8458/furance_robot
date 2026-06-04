import api from '.'

export const systemLogsApi = {
  // backend
  listBackendDates: () => api.get('/system/logs/backend'),
  viewBackend: (date, tail) => api.get(`/system/logs/backend/${date}`, { params: tail ? { tail } : {} }),
  downloadBackend: (date) => `/api/v1/system/logs/backend/${date}/download`,
  // ros2 nodes
  listRos2Dates: () => api.get('/system/logs/ros2-nodes'),
  viewRos2: (date, tail) => api.get(`/system/logs/ros2-nodes/${date}`, { params: tail ? { tail } : {} }),
  downloadRos2Node: (node, date) => `/api/v1/system/logs/ros2-nodes/${node}/${date}/download`,
}
