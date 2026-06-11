import api from '.'

const ROBOT_ID = 'robot_001'

export const cameraApi = {
  list: () => api.get(`/robot/${ROBOT_ID}/camera/list`),
  startStream: (cameraId, streamType = 'raw') =>
    api.post(`/robot/${ROBOT_ID}/camera/stream/start`, {
      camera_id: cameraId,
      stream_type: streamType,
    }),
  stopStream: (cameraId) =>
    api.post(`/robot/${ROBOT_ID}/camera/stream/stop`, {
      camera_id: cameraId,
    }),
  detect: (cameraId, scene) =>
    api.post(`/robot/${ROBOT_ID}/camera/detect`, {
      camera_id: cameraId,
      scene,
    }),
}
