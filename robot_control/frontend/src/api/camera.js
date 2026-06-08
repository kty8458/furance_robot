import api from '.'

const ROBOT_ID = 'robot_001'

export const cameraApi = {
  startPublish: (cameraId, enableRviz = false) => api.post(`/robot/${ROBOT_ID}/camera/publish/start`, { camera_id: cameraId, enable_rviz: enableRviz }),
  stopPublish: () => api.post(`/robot/${ROBOT_ID}/camera/publish/stop`),
  startStream: (cameraId, streamType) => api.post(`/robot/${ROBOT_ID}/camera/stream/start`, { camera_id: cameraId, stream_type: streamType }),
  stopStream: () => api.post(`/robot/${ROBOT_ID}/camera/stream/stop`),
  getFrame: (cameraId) => `/api/v1/robot/${ROBOT_ID}/camera/frame?camera_id=${cameraId}`,
  detect: (cameraId, scene) => api.post(`/robot/${ROBOT_ID}/camera/detect`, { camera_id: cameraId, scene }),
}
