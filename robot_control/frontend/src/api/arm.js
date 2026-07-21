import api from '.'

const ROBOT_ID = 'robot_001'

export const armApi = {
  move: (params) => api.post(`/robot/${ROBOT_ID}/arm/move`, params),
  teachSave: (arm, name, method, workflow) => api.post(`/robot/${ROBOT_ID}/arm/teach/save`, { arm, name, method }, { params: workflow ? { workflow } : {} }),
  teachUpdate: (arm, name, method, workflow) => api.put(`/robot/${ROBOT_ID}/arm/teach/${name}`, { arm, name, method }, { params: workflow ? { workflow } : {} }),
  teachList: (workflow) => api.get(`/robot/${ROBOT_ID}/arm/teach/list`, { params: workflow ? { workflow } : {} }),
  teachExec: (arm, name, method, workflow) => api.post(`/robot/${ROBOT_ID}/arm/teach/exec`, method ? { arm, name, method } : { arm, name }, { params: workflow ? { workflow } : {} }),
  teachDelete: (name, workflow) => api.delete(`/robot/${ROBOT_ID}/arm/teach/${name}`, { params: workflow ? { workflow } : {} }),
  teachCompose: (left_name, right_name, composed_name, overwrite = false) =>
    api.post(`/robot/${ROBOT_ID}/arm/teach/compose`, { left_name, right_name, composed_name, overwrite }),
}
