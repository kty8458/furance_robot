import api from '.'

export const navigationApi = {
  refreshToken: () => api.post('/navigation/token/refresh'),
  getMaps: () => api.get('/navigation/maps'),
  getPositions: (mapName) => api.get('/navigation/positions', { params: { map_name: mapName } }),
  getGraphPaths: (mapName) => api.get('/navigation/graph-paths', { params: { map_name: mapName } }),
  getRecordPaths: (mapName) => api.get('/navigation/record-paths', { params: { map_name: mapName } }),
  startTask: (params) => api.post('/navigation/task/start', params),
  stopTask: () => api.post('/navigation/task/stop'),
  getTaskStatus: () => api.get('/navigation/task/status'),
  getQueueStatus: () => api.get('/navigation/task/queue-status'),
  recharge: (mapName, pointName) => api.post('/navigation/recharge', { map_name: mapName, point_name: pointName }),
  moveWithParams: (params) => api.post('/navigation/move_with_params', params),
  cancelMoveWithParams: () => api.post('/navigation/cancel_move_with_params'),
}
