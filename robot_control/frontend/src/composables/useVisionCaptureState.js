import { reactive, watch } from 'vue'

/**
 * 全局视觉采集状态 (跨页面切换缓存)。
 *
 * 缓存相机/流/场景/照片集的当前选择, 并持久化到 localStorage。
 * 切到机械臂页移动机械臂后切回相机页, 可据此恢复选择 + 自动重连彩色流,
 * 直接点「拍照」即可, 减少操作流程。
 *
 * 注意: 不缓存 WS 连接本身 (切走时仍断开), 只缓存「是否曾连彩色流」用于自动重连。
 */

const STORAGE_KEY = 'furance.visionCapture.v1'

const DEFAULT_STATE = {
  cameraId: '',
  streamType: 'raw',
  sceneId: '',
  albumId: '',
  wasStreamingColor: false, // 上次离开时是否在连彩色 (raw/color/annotated) 流
}

function _load() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { ...DEFAULT_STATE }
    return { ...DEFAULT_STATE, ...JSON.parse(raw) }
  } catch (e) {
    return { ...DEFAULT_STATE }
  }
}

const state = reactive(_load())

function persist() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...state }))
  } catch (e) {
    /* ignore quota errors */
  }
}

// 任一字段变化即持久化
watch(state, persist, { deep: true })

export function useVisionCaptureState() {
  function set(cameraId, streamType, sceneId, albumId) {
    if (cameraId !== undefined) state.cameraId = cameraId
    if (streamType !== undefined) state.streamType = streamType
    if (sceneId !== undefined) state.sceneId = sceneId
    if (albumId !== undefined) state.albumId = albumId
  }

  function setStreamingColor(active) {
    state.wasStreamingColor = !!active
  }

  function reset() {
    Object.assign(state, DEFAULT_STATE)
    persist()
  }

  return { state, set, setStreamingColor, reset }
}
