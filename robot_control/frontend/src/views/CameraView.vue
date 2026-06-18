<template>
  <div class="tech-page">
    <el-row :gutter="16">
      <el-col :xs="24" :sm="8" :md="6">
        <el-card class="tech-card" style="margin-bottom: 16px">
          <template #header>
            <div class="tech-card-header">
              <el-icon><View /></el-icon>
              <span style="margin-left: 8px">相机选择</span>
            </div>
          </template>
          <div style="margin-bottom: 12px">
            <div style="font-size: 12px; color: #9ca3af; margin-bottom: 4px">相机</div>
            <el-select v-model="cameraId" style="width: 100%" @change="onCameraChange" @visible-change="onDropdownToggle">
              <el-option
                v-for="cam in cameras"
                :key="cam.id"
                :label="`${cam.name} (${cam.id})`"
                :value="cam.id"
                :disabled="!cam.connected"
              />
            </el-select>
          </div>
          <div style="margin-bottom: 12px">
            <div style="font-size: 12px; color: #9ca3af; margin-bottom: 4px">视频类型</div>
            <el-select v-model="streamType" style="width: 100%" :disabled="streaming">
              <el-option label="原始画面" value="raw" />
              <el-option label="深度图" value="depth" />
              <el-option label="红外图" value="ir" />
              <el-option label="带框标注" value="annotated" />
              <el-option label="红外标注" value="ir_annotated" />
            </el-select>
          </div>
          <el-row :gutter="8">
            <el-col :span="12">
              <el-button type="primary" size="small" style="width: 100%" @click="connectStream" :loading="connecting" :disabled="streaming">
                {{ streaming ? '已连接' : '连接' }}
              </el-button>
            </el-col>
            <el-col :span="12">
              <el-button type="danger" size="small" style="width: 100%" @click="disconnectStream" :disabled="!streaming">
                断开
              </el-button>
            </el-col>
          </el-row>
          <div v-if="streaming" style="margin-top: 8px; font-size: 11px; color: #00ff88">
            {{ cameraId }} / {{ streamTypeLabel }} — 推流中
          </div>
        </el-card>

        <el-card class="tech-card">
          <template #header>
            <div class="tech-card-header">
              <el-icon><Aim /></el-icon>
              <span style="margin-left: 8px">抓取检测</span>
            </div>
          </template>
          <div style="margin-bottom: 10px">
            <div style="font-size: 12px; color: #9ca3af; margin-bottom: 4px">场景</div>
            <el-input v-model="detectScene" placeholder="例如: grasp_top" size="small" />
          </div>
          <el-button size="small" type="success" style="width: 100%" @click="runDetection" :loading="detecting">
            执行检测
          </el-button>
          <div v-if="detectResult" class="detect-result">
            <div class="detect-title">抓取位姿</div>
            <el-row :gutter="4">
              <el-col :span="4" v-for="f in poseFields" :key="f">
                <div class="detect-field">
                  <div class="detect-label">{{ f }}</div>
                  <div class="detect-value">{{ detectResult[f]?.toFixed(2) ?? '--' }}</div>
                </div>
              </el-col>
            </el-row>
          </div>
        </el-card>

        <el-card class="tech-card" style="margin-top: 16px">
          <template #header>
            <div class="tech-card-header">
              <el-icon><Connection /></el-icon>
              <span style="margin-left: 8px">现场标定</span>
            </div>
          </template>

          <div style="margin-bottom: 10px">
            <div style="font-size: 12px; color: #9ca3af; margin-bottom: 4px">相机</div>
            <el-select v-model="calibCameraId" style="width: 100%">
              <el-option v-for="cam in cameras" :key="cam.id"
                :label="`${cam.name} (${cam.id})`" :value="cam.id"
                :disabled="!cam.connected" />
            </el-select>
          </div>

          <div style="margin-bottom: 10px">
            <div style="font-size: 12px; color: #9ca3af; margin-bottom: 4px">手臂</div>
            <el-select v-model="calibArm" style="width: 100%">
              <el-option label="左臂" value="left" />
              <el-option label="右臂" value="right" />
            </el-select>
          </div>

          <div style="margin-bottom: 10px">
            <div style="font-size: 12px; color: #9ca3af; margin-bottom: 4px">场景</div>
            <div style="display: flex; gap: 6px">
              <el-select v-model="calibSceneId" style="flex: 1" filterable clearable
                placeholder="选择已有场景" @change="onCalibSceneChange">
                <el-option v-for="s in sceneList" :key="s.scene_id"
                  :label="`${s.scene_id} (${s.description})`" :value="s.scene_id" />
              </el-select>
              <el-button size="small" @click="showNewScene = !showNewScene">
                {{ showNewScene ? '取消' : '新建' }}
              </el-button>
            </div>
            <div v-if="showNewScene" style="margin-top: 6px; display: flex; gap: 6px">
              <el-input v-model="newSceneId" placeholder="场景ID" size="small" style="flex: 1" />
              <el-input v-model="newSceneDesc" placeholder="描述" size="small" style="flex: 1" />
              <el-button size="small" type="primary" @click="createScene">创建</el-button>
            </div>
          </div>

          <div style="margin-bottom: 10px">
            <div style="font-size: 12px; color: #9ca3af; margin-bottom: 4px">标定点名</div>
            <el-input v-model="calibPointName" placeholder="例如: 主放置位" size="small" />
          </div>

          <el-row :gutter="8" style="margin-bottom: 10px">
            <el-col :span="12">
              <div style="font-size: 12px; color: #9ca3af; margin-bottom: 4px">QR ID</div>
              <el-input-number v-model="calibQrId" :min="0" size="small" controls-position="right" style="width: 100%" />
            </el-col>
            <el-col :span="12">
              <div style="font-size: 12px; color: #9ca3af; margin-bottom: 4px">QR 尺寸 (m)</div>
              <el-input-number v-model="calibMarkerSize" :min="0.01" :step="0.001" :precision="3"
                size="small" controls-position="right" style="width: 100%" />
            </el-col>
          </el-row>

          <el-button size="small" type="success" style="width: 100%" @click="runCalibration" :loading="calibrating">
            执行标定
          </el-button>

          <div v-if="calibResult" class="detect-result" style="margin-top: 10px">
            <div class="detect-title">标定结果 — T_qr_workspace</div>
            <div style="font-size: 11px; color: #9ca3af; margin-bottom: 4px">Translation (m)</div>
            <div style="font-family: 'Consolas', monospace; font-size: 12px; color: #e5e7eb">
              x: {{ calibResult.translation?.[0]?.toFixed(4) ?? '--' }}
              y: {{ calibResult.translation?.[1]?.toFixed(4) ?? '--' }}
              z: {{ calibResult.translation?.[2]?.toFixed(4) ?? '--' }}
            </div>
            <div style="font-size: 11px; color: #9ca3af; margin-bottom: 4px; margin-top: 4px">Rotation (xyzw)</div>
            <div style="font-family: 'Consolas', monospace; font-size: 12px; color: #e5e7eb">
              x: {{ calibResult.rotation?.[0]?.toFixed(4) ?? '--' }}
              y: {{ calibResult.rotation?.[1]?.toFixed(4) ?? '--' }}
              z: {{ calibResult.rotation?.[2]?.toFixed(4) ?? '--' }}
              w: {{ calibResult.rotation?.[3]?.toFixed(4) ?? '--' }}
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :xs="24" :sm="16" :md="18">
        <el-card class="tech-card">
          <template #header>
            <div class="tech-card-header">
              <el-icon><VideoCamera /></el-icon>
              <span style="margin-left: 8px">
                {{ streaming ? `${cameraId} / ${streamTypeLabel}` : '未连接' }}
              </span>
            </div>
          </template>
          <div class="video-container">
            <img v-if="streaming && frameData" :src="frameData" class="video-frame" alt="Camera feed" />
            <div v-else class="video-placeholder">
              <el-icon style="font-size: 48px; color: #2a3a4a"><VideoCamera /></el-icon>
              <div style="margin-top: 12px; color: #6b7b8d">点击「连接」开始查看视频</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { cameraApi } from '../api/camera'
import { ElMessage } from 'element-plus'
import { View, Aim, VideoCamera, Connection } from '@element-plus/icons-vue'

const poseFields = ['x', 'y', 'z', 'roll', 'pitch', 'yaw']

const cameras = ref([])
const cameraId = ref('')
const streamType = ref('raw')
const streaming = ref(false)
const connecting = ref(false)
const detectScene = ref('grasp_top')
const detecting = ref(false)
const detectResult = ref(null)

// ---- 标定状态 ----
const calibCameraId = ref('head')
const calibArm = ref('right')
const calibSceneId = ref('')
const calibPointName = ref('')
const calibQrId = ref(0)
const calibMarkerSize = ref(0.058)
const calibrating = ref(false)
const calibResult = ref(null)
const sceneList = ref([])
const showNewScene = ref(false)
const newSceneId = ref('')
const newSceneDesc = ref('')

let ws = null
const frameData = ref('')

const streamTypeLabel = computed(() => {
  const labels = { raw: '原始画面', depth: '深度图', ir: '红外图', annotated: '带框标注', ir_annotated: '红外标注' }
  return labels[streamType.value] || streamType.value
})

async function loadCameras() {
  try {
    const res = await cameraApi.list()
    cameras.value = res.data || []
    if (cameras.value.length && !cameras.value.find(c => c.id === cameraId.value)) {
      cameraId.value = cameras.value[0].id
    }
  } catch (e) {
    ElMessage.error('获取相机列表失败')
  }
}

onUnmounted(() => disconnectStream())

watch(() => cameraId.value, () => {
  if (streaming.value) { disconnectStream(); setTimeout(connectStream, 300) }
})

function getWsUrl() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws/v1/camera`
}

async function connectStream() {
  connecting.value = true
  try {
    await cameraApi.startStream(cameraId.value, streamType.value)
    ws = new WebSocket(getWsUrl())
    ws.onopen = () => {
      ws.send(JSON.stringify({ action: 'subscribe', camera_id: cameraId.value, stream_type: streamType.value }))
      streaming.value = true
      connecting.value = false
      ElMessage.success(`已连接 ${cameraId.value}`)
    }
    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        if (msg.type === 'frame' && msg.data) {
          frameData.value = 'data:image/jpeg;base64,' + msg.data
        } else if (msg.type === 'error') {
          ElMessage.error(msg.message)
        }
      } catch (e) { /* ignore */ }
    }
    ws.onerror = () => { ElMessage.error('WebSocket 错误'); disconnectStream() }
    ws.onclose = () => { streaming.value = false; frameData.value = '' }
  } catch (e) {
    ElMessage.error(e.message || '连接失败')
    connecting.value = false
  }
}

function disconnectStream() {
  if (ws) {
    try { ws.send(JSON.stringify({ action: 'unsubscribe' })) } catch (e) { /* ignore */ }
    ws.close(); ws = null
  }
  streaming.value = false; frameData.value = ''
  cameraApi.stopStream(cameraId.value).catch(() => {})
}

function onDropdownToggle(visible) {
  if (visible) { loadCameras(); loadSceneList() }
}

onMounted(() => {
  loadCameras()
  loadSceneList()
})

function onCameraChange() {
  if (streaming.value) { disconnectStream(); setTimeout(connectStream, 300) }
}

async function runDetection() {
  detecting.value = true
  try {
    const res = await cameraApi.detect(cameraId.value, detectScene.value)
    detectResult.value = res.data?.data?.grasp_pose || res.data?.grasp_pose || res.data
    ElMessage.success('检测完成')
  } catch (e) {
    ElMessage.error(e.message || '检测失败')
  } finally {
    detecting.value = false
  }
}

async function loadSceneList() {
  try {
    const res = await cameraApi.scene('list')
    sceneList.value = res.data || []
  } catch { sceneList.value = [] }
}

async function createScene() {
  if (!newSceneId.value) { ElMessage.warning('请输入场景ID'); return }
  try {
    await cameraApi.scene('create', newSceneId.value, { description: newSceneDesc.value })
    ElMessage.success(`场景 ${newSceneId.value} 已创建`)
    calibSceneId.value = newSceneId.value
    showNewScene.value = false
    newSceneId.value = ''
    newSceneDesc.value = ''
    await loadSceneList()
  } catch (e) { ElMessage.error(e.message || '创建失败') }
}

function onCalibSceneChange() { /* placeholder */ }

async function runCalibration() {
  if (!calibSceneId.value) { ElMessage.warning('请选择场景'); return }
  if (!calibPointName.value) { ElMessage.warning('请输入标定点名'); return }
  calibrating.value = true
  calibResult.value = null
  try {
    const res = await cameraApi.calibrate({
      camera_id: calibCameraId.value,
      arm: calibArm.value,
      qr_id: calibQrId.value,
      marker_size: calibMarkerSize.value,
      point_name: calibPointName.value,
      scene_id: calibSceneId.value,
    })
    calibResult.value = res.data || res
    ElMessage.success('标定完成')
  } catch (e) {
    ElMessage.error(e.message || '标定失败')
  } finally {
    calibrating.value = false
  }
}
</script>

<style scoped>
.video-container { width: 100%; min-height: 360px; background: #050a10; border-radius: 8px; display: flex; align-items: center; justify-content: center; overflow: hidden; }
.video-frame { width: 100%; height: auto; display: block; }
.video-placeholder { text-align: center; }
.detect-result { margin-top: 10px; padding: 8px; background: #0d1a26; border: 1px solid #2a3a4a; border-radius: 6px; }
.detect-title { font-size: 12px; color: #00d4ff; margin-bottom: 6px; }
.detect-field { text-align: center; }
.detect-label { font-size: 10px; color: #6b7b8d; }
.detect-value { font-family: 'Consolas', monospace; font-size: 12px; color: #e5e7eb; }
</style>
