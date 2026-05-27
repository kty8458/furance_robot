import api from '.'

const ROBOT_ID = 'robot_001'

export const upperBodyApi = {
  waist: (params) => api.post(`/robot/${ROBOT_ID}/upper-body/waist`, params),
  ascend: (params) => api.post(`/robot/${ROBOT_ID}/upper-body/ascend`, params),
  head: (params) => api.post(`/robot/${ROBOT_ID}/upper-body/head`, params),
}
