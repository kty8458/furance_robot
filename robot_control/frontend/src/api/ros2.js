import api from '.'

export const ros2Api = {
  listNodes: () => api.get('/ros2/nodes'),
  startNode: (name) => api.post(`/ros2/nodes/${name}/start`),
  stopNode: (name) => api.post(`/ros2/nodes/${name}/stop`),
  nodeStatus: (name) => api.get(`/ros2/nodes/${name}/status`),

  listLaunches: () => api.get('/ros2/launches'),
  startLaunch: (name) => api.post(`/ros2/launches/${name}/start`),
  stopLaunch: (name) => api.post(`/ros2/launches/${name}/stop`),
  launchStatus: (name) => api.get(`/ros2/launches/${name}/status`),
}
