import api from '.'

export const ros2Api = {
  listNodes: () => api.get('/ros2/nodes'),
  startNode: (name) => api.post(`/ros2/nodes/${name}/start`),
  stopNode: (name) => api.post(`/ros2/nodes/${name}/stop`),
  nodeStatus: (name) => api.get(`/ros2/nodes/${name}/status`),
}
