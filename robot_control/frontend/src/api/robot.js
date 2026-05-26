import api from '.'

const ROBOT_ID = 'robot_001'

export const robotApi = {
  home: () => api.post(`/robot/${ROBOT_ID}/home`),
  grab: (target) => api.post(`/robot/${ROBOT_ID}/grab`, { target }),
  place: (target) => api.post(`/robot/${ROBOT_ID}/place`, { target }),
  gripper: (arm, action, force) => api.post(`/robot/${ROBOT_ID}/gripper`, { arm, action, force }),
  lift: (direction, height) => api.post(`/robot/${ROBOT_ID}/lift`, { direction, height }),
  charge: (action) => api.post(`/robot/${ROBOT_ID}/charge`, { action }),
  enable: (enable) => api.post(`/robot/${ROBOT_ID}/enable`, { enable, clear_error: false }),
  clearError: () => api.post(`/robot/${ROBOT_ID}/clear-error`),
}
