import api from '.'

const ROBOT_ID = 'robot_001'

export const photoApi = {
  capture: (data) =>
    api.post(`/robot/${ROBOT_ID}/camera/photos/capture`, data),
  listAlbums: (sceneId) =>
    api.get(`/robot/${ROBOT_ID}/camera/photos/${sceneId}/albums`),
  createAlbum: (sceneId, name) =>
    api.post(`/robot/${ROBOT_ID}/camera/photos/${sceneId}/albums`, { name }),
  deleteAlbum: (sceneId, albumId) =>
    api.delete(`/robot/${ROBOT_ID}/camera/photos/${sceneId}/albums/${albumId}`),
  listPhotos: (sceneId, albumId) =>
    api.get(`/robot/${ROBOT_ID}/camera/photos/${sceneId}/albums/${albumId}/photos`),
  deletePhoto: (sceneId, albumId, photoId) =>
    api.delete(`/robot/${ROBOT_ID}/camera/photos/${sceneId}/albums/${albumId}/photos/${photoId}`),
  // 单张查看/下载 - 直接拼 URL, 供 <img> src 使用
  photoFileUrl: (sceneId, albumId, photoId) =>
    `/api/v1/robot/${ROBOT_ID}/camera/photos/${sceneId}/albums/${albumId}/photos/${photoId}/file`,
  // 打包下载 zip - window.location 触发浏览器下载
  albumDownloadUrl: (sceneId, albumId) =>
    `/api/v1/robot/${ROBOT_ID}/camera/photos/${sceneId}/albums/${albumId}/download`,
}
