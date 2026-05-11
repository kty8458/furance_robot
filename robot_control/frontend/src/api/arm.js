import api from '.'

const ROBOT_ID = 'robot_001'

export const armApi = {
  move: (params) => api.post(`/robot/${ROBOT_ID}/arm/move`, params),
  teachSave: (arm, name) => api.post(`/robot/${ROBOT_ID}/arm/teach/save`, { arm, name }),
  teachList: () => api.get(`/robot/${ROBOT_ID}/arm/teach/list`),
  teachExec: (arm, name) => api.post(`/robot/${ROBOT_ID}/arm/teach/exec`, { arm, name }),
  teachDelete: (name) => api.delete(`/robot/${ROBOT_ID}/arm/teach/${name}`),
}
