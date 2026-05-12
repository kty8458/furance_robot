import axios from 'axios'

const api = axios.create({ baseURL: '/api/v1' })

// 自动解包 {code, message, data} 响应格式
api.interceptors.response.use(
  (response) => {
    const body = response.data
    if (body && typeof body === 'object' && 'code' in body) {
      if (body.code === 0) {
        return { data: body.data }
      }
      return Promise.reject(new Error(body.message || '请求失败'))
    }
    return response
  },
  (error) => Promise.reject(error)
)

export default api
