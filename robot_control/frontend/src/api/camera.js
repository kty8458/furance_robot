import api from '.'

const ROBOT_ID = 'robot_001'

export const cameraApi = {
  /** 获取相机列表 */
  list: () => api.get(`/robot/${ROBOT_ID}/camera/list`),

  /** 启动相机帧采集 */
  startStream: (cameraId, streamType = 'raw') =>
    api.post(`/robot/${ROBOT_ID}/camera/stream/start`, {
      camera_id: cameraId,
      stream_type: streamType,
    }),

  /** 停止相机帧采集 */
  stopStream: (cameraId) =>
    api.post(`/robot/${ROBOT_ID}/camera/stream/stop`, {
      camera_id: cameraId,
    }),

  /** 执行视觉检测 */
  detect: (cameraId, scene) =>
    api.post(`/robot/${ROBOT_ID}/camera/detect`, {
      camera_id: cameraId,
      scene,
    }),
}
