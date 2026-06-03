import api from '.'

const ROBOT_ID = 'robot_001'

export const armApi = {
  move: (params) => api.post(`/robot/${ROBOT_ID}/arm/move`, params),
  teachSave: (arm, name, method) => api.post(`/robot/${ROBOT_ID}/arm/teach/save`, { arm, name, method }),
  teachUpdate: (arm, name, method) => api.put(`/robot/${ROBOT_ID}/arm/teach/${name}`, { arm, name, method }),
  teachList: () => api.get(`/robot/${ROBOT_ID}/arm/teach/list`),
  teachExec: (arm, name, method) => api.post(`/robot/${ROBOT_ID}/arm/teach/exec`, method ? { arm, name, method } : { arm, name }),
  teachDelete: (name) => api.delete(`/robot/${ROBOT_ID}/arm/teach/${name}`),
}
