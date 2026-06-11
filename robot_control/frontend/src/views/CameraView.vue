<template>
  <div class="tech-page">
    <el-row :gutter="16">
      <!-- Camera selection & controls -->
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
            <el-select v-model="cameraId" style="width: 100%" @change="onCameraChange">
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
              <el-option label="带框标注" value="annotated" :disabled="true" />
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

        <!-- Vision detection -->
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
      </el-col>

      <!-- Video display -->
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
            <img
              v-if="streaming && frameData"
              :src="frameData"
              class="video-frame"
              alt="Camera feed"
            />
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
import { View, Aim, VideoCamera } from '@element-plus/icons-vue'

const poseFields = ['x', 'y', 'z', 'roll', 'pitch', 'yaw']

// ---- 相机列表 ----
const cameras = ref([])
const cameraId = ref('head')
const streamType = ref('raw')
const streaming = ref(false)
const connecting = ref(false)

// ---- 视觉检测 ----
const detectScene = ref('grasp_top')
const detecting = ref(false)
const detectResult = ref(null)

// ---- WebSocket ----
let ws = null
const frameData = ref('')

const streamTypeLabel = computed(() => {
  const labels = { raw: '原始画面', depth: '深度图', annotated: '带框标注' }
  return labels[streamType.value] || streamType.value
})

// 加载相机列表
async function loadCameras() {
  try {
    const res = await cameraApi.list()
    cameras.value = res.data || []
    if (cameras.value.length > 0 && !cameras.value.find(c => c.id === cameraId.value)) {
      cameraId.value = cameras.value[0].id
    }
  } catch (e) {
    ElMessage.error('获取相机列表失败')
    cameras.value = []
  }
}

onMounted(loadCameras)

onUnmounted(() => {
  disconnectStream()
})

watch(() => cameraId.value, () => {
  if (streaming.value) {
    disconnectStream()
    setTimeout(connectStream, 300)
  }
})

// ---- WebSocket 连接 ----

function getWsUrl() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws/v1/camera`
}

async function connectStream() {
  connecting.value = true
  try {
    // 先通过 HTTP 启动相机流采集
    await cameraApi.startStream(cameraId.value, streamType.value)

    // 建立 WebSocket 连接
    const url = getWsUrl()
    ws = new WebSocket(url)

    ws.onopen = () => {
      ws.send(JSON.stringify({
        action: 'subscribe',
        camera_id: cameraId.value,
        stream_type: streamType.value,
      }))
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
      } catch (e) {
        // ignore parse errors
      }
    }

    ws.onerror = () => {
      ElMessage.error('WebSocket 连接错误')
      disconnectStream()
    }

    ws.onclose = () => {
      if (streaming.value) {
        streaming.value = false
        frameData.value = ''
      }
    }
  } catch (error) {
    ElMessage.error(error.message || '连接失败')
    connecting.value = false
  }
}

function disconnectStream() {
  if (ws) {
    try {
      ws.send(JSON.stringify({ action: 'unsubscribe' }))
    } catch (e) { /* ignore */ }
    ws.close()
    ws = null
  }
  streaming.value = false
  frameData.value = ''
  cameraApi.stopStream(cameraId.value).catch(() => {})
}

function onCameraChange() {
  if (streaming.value) {
    disconnectStream()
    setTimeout(connectStream, 300)
  }
}

// ---- 视觉检测 ----

async function runDetection() {
  detecting.value = true
  try {
    const res = await cameraApi.detect(cameraId.value, detectScene.value)
    const data = res.data?.data || res.data
    detectResult.value = data?.grasp_pose || data
    ElMessage.success('检测完成')
  } catch (error) {
    ElMessage.error(error.message || '检测失败')
  } finally {
    detecting.value = false
  }
}
</script>

<style scoped>
.video-container {
  width: 100%;
  min-height: 360px;
  background: #050a10;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
.video-frame {
  width: 100%;
  height: auto;
  display: block;
}
.video-placeholder {
  text-align: center;
}
.detect-result {
  margin-top: 10px;
  padding: 8px;
  background: #0d1a26;
  border: 1px solid #2a3a4a;
  border-radius: 6px;
}
.detect-title {
  font-size: 12px;
  color: #00d4ff;
  margin-bottom: 6px;
}
.detect-field {
  text-align: center;
}
.detect-label {
  font-size: 10px;
  color: #6b7b8d;
}
.detect-value {
  font-family: 'Consolas', monospace;
  font-size: 12px;
  color: #e5e7eb;
}
</style>
