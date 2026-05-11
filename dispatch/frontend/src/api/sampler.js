import api from '.'

export const samplerApi = {
  sendCommand: (command, params) => api.post('/dispatch/sampler/command', { command, params }),
  getStatus: () => api.get('/dispatch/sampler/status'),
}