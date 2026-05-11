import api from '.'

export const robotApi = {
  home: (robotId) => api.post(`/dispatch/robot/${robotId}/home`),
  grab: (robotId, target) => api.post(`/dispatch/robot/${robotId}/grab`, { target }),
  place: (robotId, target) => api.post(`/dispatch/robot/${robotId}/place`, { target }),
  gripper: (robotId, arm, action, force) => api.post(`/dispatch/robot/${robotId}/gripper`, { arm, action, force }),
  lift: (robotId, direction, height) => api.post(`/dispatch/robot/${robotId}/lift`, { direction, height }),
  charge: (robotId, action) => api.post(`/dispatch/robot/${robotId}/charge`, { action }),
  enable: (robotId, enable, clearError) => api.post(`/dispatch/robot/${robotId}/enable`, { enable, clear_error: clearError }),
  getStatus: (robotId) => api.get(`/dispatch/robot/${robotId}/status`),
  listRobots: () => api.get('/dispatch/robots'),
}