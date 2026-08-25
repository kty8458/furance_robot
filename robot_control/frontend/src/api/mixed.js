import api from '.'

const ROBOT_ID = 'robot_001'

export const mixedApi = {
  listFunctions: () => api.get(`/robot/${ROBOT_ID}/mixed/functions`),
}
