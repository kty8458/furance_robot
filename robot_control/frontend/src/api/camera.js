import api from '.'

const ROBOT_ID = 'robot_001'

export const cameraApi = {
  startStream: (cameraId, streamType) => api.post(`/robot/${ROBOT_ID}/camera/stream/start`, { camera_id: cameraId, stream_type: streamType }),
  stopStream: () => api.post(`/robot/${ROBOT_ID}/camera/stream/stop`),
  getFrame: (cameraId) => `/api/v1/robot/${ROBOT_ID}/camera/frame?camera_id=${cameraId}`,
  detect: (cameraId, scene) => api.post(`/robot/${ROBOT_ID}/camera/detect`, { camera_id: cameraId, scene }),
}
