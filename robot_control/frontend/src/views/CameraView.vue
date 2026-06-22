<template>
  <div class="tech-page">
    <!-- ====== 上部分: 相机选择 + 视频 ====== -->
    <el-row :gutter="16" style="margin-bottom: 16px">
      <el-col :xs="24" :sm="6" :md="5">
        <el-card class="tech-card">
          <template #header>
            <div class="tech-card-header">
              <el-icon><View /></el-icon>
              <span style="margin-left: 8px">相机选择</span>
            </div>
          </template>
          <div style="margin-bottom: 10px">
            <div class="field-label">相机</div>
            <el-select v-model="cameraId" style="width: 100%" @change="onCameraChange" @visible-change="onDropdownToggle">
              <el-option v-for="cam in cameras" :key="cam.id"
                :label="`${cam.name} (${cam.id})`" :value="cam.id" :disabled="!cam.connected" />
            </el-select>
          </div>
          <div style="margin-bottom: 10px">
            <div class="field-label">视频类型</div>
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
              <el-button type="danger" size="small" style="width: 100%" @click="disconnectStream" :disabled="!streaming">断开</el-button>
            </el-col>
          </el-row>
          <div v-if="streaming" style="margin-top: 8px; font-size: 11px; color: #00ff88">
            {{ cameraId }} / {{ streamTypeLabel }} — 推流中
          </div>
        </el-card>
      </el-col>

      <el-col :xs="24" :sm="18" :md="19">
        <el-card class="tech-card">
          <template #header>
            <div class="tech-card-header">
              <el-icon><VideoCamera /></el-icon>
              <span style="margin-left: 8px">{{ streaming ? `${cameraId} / ${streamTypeLabel}` : '未连接' }}</span>
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

    <!-- ====== 下部分: 现场标定 ====== -->
    <el-card class="tech-card">
      <template #header>
        <div class="tech-card-header">
          <el-icon><Connection /></el-icon>
          <span style="margin-left: 8px">现场标定</span>
        </div>
      </template>

      <el-row :gutter="16">
        <!-- 第一部分: 场景 & 点位管理 -->
        <el-col :xs="24" :md="12">
          <div class="section-title">场景 & 点位管理</div>

          <!-- 场景操作 -->
          <div style="margin-bottom: 10px">
            <div class="field-label">场景</div>
            <div style="display: flex; gap: 6px">
              <el-select v-model="mgmtSceneId" style="flex: 1" filterable clearable placeholder="选择场景" @change="onMgmtSceneChange">
                <el-option v-for="s in sceneList" :key="s.scene_id" :label="`${s.scene_id} (${s.description})`" :value="s.scene_id" />
              </el-select>
              <el-button size="small" @click="showNewScene = !showNewScene">{{ showNewScene ? '取消' : '新建' }}</el-button>
              <el-button size="small" type="danger" @click="deleteCurrentScene" :disabled="!mgmtSceneId">删除</el-button>
            </div>
            <div v-if="showNewScene" style="margin-top: 6px; display: flex; gap: 6px">
              <el-input v-model="newSceneId" placeholder="场景ID" size="small" style="flex: 1" />
              <el-input v-model="newSceneDesc" placeholder="描述" size="small" style="flex: 1" />
              <el-button size="small" type="primary" @click="createScene">创建</el-button>
            </div>
          </div>

          <!-- 点位列表 -->
          <div v-if="mgmtSceneId" style="margin-bottom: 10px">
            <div class="field-label">点位</div>
            <div style="display: flex; gap: 6px; margin-bottom: 6px">
              <el-select v-model="mgmtPointName" style="flex: 1" filterable placeholder="选择点位" @change="onMgmtPointChange">
                <el-option v-for="p in (scenePoints[mgmtSceneId] || [])" :key="p.name" :label="p.name" :value="p.name" />
              </el-select>
              <el-button size="small" type="primary" @click="showNewPoint = true">新建点位</el-button>
              <el-button size="small" type="danger" @click="deleteCurrentPoint" :disabled="!mgmtPointName">删除</el-button>
            </div>
            <!-- 新建点位弹窗 -->
            <div v-if="showNewPoint" style="display: flex; gap: 6px; margin-bottom: 6px">
              <el-input v-model="newPointName" placeholder="点位名称" size="small" style="flex: 1" />
              <el-select v-model="newPointArm" size="small" style="width: 80px">
                <el-option label="左臂" value="left" />
                <el-option label="右臂" value="right" />
              </el-select>
              <el-button size="small" type="primary" @click="createPoint">确认</el-button>
              <el-button size="small" @click="showNewPoint = false">取消</el-button>
            </div>
          </div>

          <!-- 点位数据编辑 -->
          <div v-if="mgmtPointName && pointData" class="point-data-panel">
            <div class="field-label">点位数据 — {{ mgmtPointName }}</div>
            <el-row :gutter="6">
              <el-col :span="4" v-for="(f, fi) in poseFields" :key="'pt_'+fi">
                <div class="field-label" style="font-size: 10px">{{ f }}</div>
                <el-input-number v-model="pointData.xyzrpy[f]" size="small" :step="f==='x'||f==='y'||f==='z'?0.001:0.1"
                  :precision="f==='x'||f==='y'||f==='z'?4:2" controls-position="right" style="width: 100%" />
              </el-col>
            </el-row>
            <div style="display: flex; gap: 6px; margin-top: 8px">
              <el-button size="small" type="warning" @click="updatePointData" style="flex: 1">更新点位</el-button>
              <el-button size="small" @click="reloadScenePoints">刷新</el-button>
            </div>
          </div>
        </el-col>

        <!-- 第二部分: 视觉标定 -->
        <el-col :xs="24" :md="12">
          <div class="section-title">视觉标定</div>

          <div style="margin-bottom: 10px">
            <div class="field-label">场景</div>
            <el-select v-model="calibSceneId" style="width: 100%" filterable clearable placeholder="选择场景" @change="onCalibSceneChange">
              <el-option v-for="s in sceneList" :key="s.scene_id" :label="`${s.scene_id} (${s.description})`" :value="s.scene_id" />
            </el-select>
          </div>

          <div style="margin-bottom: 10px">
            <div class="field-label">标定点</div>
            <el-select v-model="calibPointName" style="width: 100%" filterable placeholder="选择点位" @change="onCalibPointChange">
              <el-option v-for="p in (scenePoints[calibSceneId] || [])" :key="p.name" :label="p.name" :value="p.name" />
            </el-select>
          </div>

          <div v-if="calibPointName" style="font-size: 10px; color: #6b7b8d; margin-bottom: 10px">
            自动读取: 相机={{ calibCameraId }} 手臂={{ calibArm }}
          </div>

          <div style="margin-bottom: 10px">
            <div class="field-label">标定视频流</div>
            <el-radio-group v-model="calibStreamType" size="small">
              <el-radio-button value="color">彩色</el-radio-button>
              <el-radio-button value="ir">红外</el-radio-button>
            </el-radio-group>
          </div>

          <el-row :gutter="8" style="margin-bottom: 10px">
            <el-col :span="12">
              <div class="field-label">QR ID</div>
              <el-input-number v-model="calibQrId" :min="0" size="small" controls-position="right" style="width: 100%" />
            </el-col>
            <el-col :span="12">
              <div class="field-label">QR 尺寸 (m)</div>
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
        </el-col>
      </el-row>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { cameraApi } from '../api/camera'
import { ElMessage, ElMessageBox } from 'element-plus'
import { View, VideoCamera, Connection } from '@element-plus/icons-vue'

const poseFields = ['x', 'y', 'z', 'roll', 'pitch', 'yaw']

// ---- 相机 / 视频 ----
const cameras = ref([])
const cameraId = ref('')
const streamType = ref('raw')
const streaming = ref(false)
const connecting = ref(false)
let ws = null
const frameData = ref('')

const streamTypeLabel = computed(() => {
  const labels = { raw: '原始画面', depth: '深度图', ir: '红外图', annotated: '带框标注', ir_annotated: '红外标注' }
  return labels[streamType.value] || streamType.value
})

// ---- 场景 & 点位管理 ----
const sceneList = ref([])
const scenePoints = ref({})          // {scene_id: [{name, arm, ...}]}
const sceneDetails = ref({})         // {scene_id: full scene data}
const mgmtSceneId = ref('')
const mgmtPointName = ref('')
const pointData = ref(null)          // { xyzrpy: {x,y,z,roll,pitch,yaw}, raw: original point dict }
const showNewScene = ref(false)
const newSceneId = ref('')
const newSceneDesc = ref('')
const showNewPoint = ref(false)
const newPointName = ref('')
const newPointArm = ref('right')

// ---- 视觉标定 ----
const calibSceneId = ref('')
const calibPointName = ref('')
const calibCameraId = ref('')
const calibArm = ref('right')
const calibStreamType = ref('color')
const calibQrId = ref(0)
const calibMarkerSize = ref(0.058)
const calibrating = ref(false)
const calibResult = ref(null)

// ========== 工具函数 ==========

function quatToEuler(qx, qy, qz, qw) {
  const R = [
    [1 - 2*qy*qy - 2*qz*qz, 2*qx*qy - 2*qz*qw, 2*qx*qz + 2*qy*qw],
    [2*qx*qy + 2*qz*qw, 1 - 2*qx*qx - 2*qz*qz, 2*qy*qz - 2*qx*qw],
    [2*qx*qz - 2*qy*qw, 2*qy*qz + 2*qx*qw, 1 - 2*qx*qx - 2*qy*qy],
  ]
  const sy = Math.sqrt(R[0][0]**2 + R[1][0]**2)
  const singular = sy < 1e-6
  let roll, pitch, yaw
  if (!singular) {
    roll = Math.atan2(R[2][1], R[2][2])
    pitch = Math.atan2(-R[2][0], sy)
    yaw = Math.atan2(R[1][0], R[0][0])
  } else {
    roll = Math.atan2(-R[1][2], R[1][1])
    pitch = Math.atan2(-R[2][0], sy)
    yaw = 0
  }
  return { roll: roll * 180 / Math.PI, pitch: pitch * 180 / Math.PI, yaw: yaw * 180 / Math.PI }
}

function eulerToQuat(roll_deg, pitch_deg, yaw_deg) {
  const roll = roll_deg * Math.PI / 180
  const pitch = pitch_deg * Math.PI / 180
  const yaw = yaw_deg * Math.PI / 180
  const cr = Math.cos(roll * 0.5), sr = Math.sin(roll * 0.5)
  const cp = Math.cos(pitch * 0.5), sp = Math.sin(pitch * 0.5)
  const cy = Math.cos(yaw * 0.5), sy = Math.sin(yaw * 0.5)
  return [
    sr * cp * cy - cr * sp * sy,
    cr * sp * cy + sr * cp * sy,
    cr * cp * sy - sr * sp * cy,
    cr * cp * cy + sr * sp * sy,
  ]
}

// ========== 相机 & 视频 ==========

async function loadCameras() {
  try {
    const res = await cameraApi.list()
    cameras.value = res.data || []
    if (cameras.value.length && !cameras.value.find(c => c.id === cameraId.value)) {
      cameraId.value = cameras.value[0].id
    }
  } catch { ElMessage.error('获取相机列表失败') }
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
      streaming.value = true; connecting.value = false
      ElMessage.success(`已连接 ${cameraId.value}`)
    }
    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        if (msg.type === 'frame' && msg.data) frameData.value = 'data:image/jpeg;base64,' + msg.data
        else if (msg.type === 'error') ElMessage.error(msg.message)
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

function onDropdownToggle(visible) { if (visible) { loadCameras(); loadSceneList() } }
function onCameraChange() { if (streaming.value) { disconnectStream(); setTimeout(connectStream, 300) } }

// ========== 场景 & 点位管理 ==========

async function loadSceneList() {
  try {
    const res = await cameraApi.scene('list')
    sceneList.value = res.data || []
  } catch { sceneList.value = [] }
}

async function loadSceneDetails(sceneId) {
  if (!sceneId) return
  try {
    const res = await cameraApi.scene('get', sceneId)
    const data = res.data || {}
    sceneDetails.value[sceneId] = data
    scenePoints.value[sceneId] = (data.qr_transforms || []).map(p => ({
      name: p.name, arm: p.arm, qr_id: p.qr_id, marker_size: p.marker_size,
      stream_type: p.stream_type || 'color',
      T_qr_workspace: p.T_qr_workspace || { translation: [0,0,0], rotation: [0,0,0,1] },
    }))
  } catch { scenePoints.value[sceneId] = [] }
}

async function reloadScenePoints() {
  if (mgmtSceneId.value) {
    sceneDetails.value[mgmtSceneId.value] = null
    await loadSceneDetails(mgmtSceneId.value)
    if (mgmtPointName.value) onMgmtPointChange(mgmtPointName.value)
  }
  if (calibSceneId.value) {
    sceneDetails.value[calibSceneId.value] = null
    await loadSceneDetails(calibSceneId.value)
  }
}

async function createScene() {
  if (!newSceneId.value) { ElMessage.warning('请输入场景ID'); return }
  try {
    await cameraApi.scene('create', newSceneId.value, { description: newSceneDesc.value })
    ElMessage.success(`场景 ${newSceneId.value} 已创建`)
    mgmtSceneId.value = newSceneId.value
    showNewScene.value = false; newSceneId.value = ''; newSceneDesc.value = ''
    await loadSceneList()
  } catch (e) { ElMessage.error(e.message || '创建失败') }
}

async function deleteCurrentScene() {
  if (!mgmtSceneId.value) return
  try {
    await ElMessageBox.confirm(`确定删除场景 "${mgmtSceneId.value}"？`, '确认删除', { type: 'warning' })
    await cameraApi.scene('delete', mgmtSceneId.value)
    ElMessage.success('场景已删除')
    mgmtSceneId.value = ''; mgmtPointName.value = ''; pointData.value = null
    await loadSceneList()
  } catch (e) { if (e !== 'cancel') ElMessage.error(e.message || '删除失败') }
}

async function onMgmtSceneChange(sceneId) {
  mgmtPointName.value = ''; pointData.value = null
  if (sceneId) await loadSceneDetails(sceneId)
}

async function createPoint() {
  if (!newPointName.value) { ElMessage.warning('请输入点位名称'); return }
  try {
    await cameraApi.scene('add_point', mgmtSceneId.value, {
      name: newPointName.value, arm: newPointArm.value,
      qr_id: 0, marker_size: 0.058, stream_type: 'color',
      T_qr_workspace: { translation: [0, 0, 0], rotation: [0, 0, 0, 1] },
    })
    ElMessage.success('点位已创建')
    showNewPoint.value = false; newPointName.value = ''
    await reloadScenePoints()
  } catch (e) { ElMessage.error(e.message || '创建点位失败') }
}

async function deleteCurrentPoint() {
  if (!mgmtPointName.value) return
  try {
    await ElMessageBox.confirm(`确定删除点位 "${mgmtPointName.value}"？`, '确认删除', { type: 'warning' })
    await cameraApi.scene('delete_point', mgmtSceneId.value, { name: mgmtPointName.value })
    ElMessage.success('点位已删除')
    mgmtPointName.value = ''; pointData.value = null
    await reloadScenePoints()
  } catch (e) { if (e !== 'cancel') ElMessage.error(e.message || '删除失败') }
}

function onMgmtPointChange(pointName) {
  if (!pointName) { pointData.value = null; return }
  const sceneId = mgmtSceneId.value
  const points = scenePoints.value[sceneId] || []
  const p = points.find(pp => pp.name === pointName)
  if (!p) { pointData.value = null; return }
  const tw = p.T_qr_workspace || {}
  const t = tw.translation || [0, 0, 0]
  const r = tw.rotation || [0, 0, 0, 1]
  const euler = quatToEuler(r[0], r[1], r[2], r[3])
  pointData.value = {
    xyzrpy: { x: t[0], y: t[1], z: t[2], roll: euler.roll, pitch: euler.pitch, yaw: euler.yaw },
    raw: p,
  }
}

async function updatePointData() {
  if (!mgmtPointName.value || !pointData.value) return
  const d = pointData.value.xyzrpy
  const quat = eulerToQuat(d.roll, d.pitch, d.yaw)
  try {
    await cameraApi.scene('update_point', mgmtSceneId.value, {
      name: mgmtPointName.value,
      T_qr_workspace: { translation: [d.x, d.y, d.z], rotation: quat },
    })
    ElMessage.success('点位数据已更新')
    await reloadScenePoints()
  } catch (e) { ElMessage.error(e.message || '更新失败') }
}

// ========== 视觉标定 ==========

async function onCalibSceneChange(sceneId) {
  calibPointName.value = ''
  if (sceneId) await loadSceneDetails(sceneId)
}

function onCalibPointChange(pointName) {
  if (!pointName) return
  const sceneId = calibSceneId.value
  const points = scenePoints.value[sceneId] || []
  const p = points.find(pp => pp.name === pointName)
  if (p) {
    calibCameraId.value = cameras.value.find(c => c.connected)?.id || ''
    calibArm.value = p.arm || 'right'
    calibQrId.value = p.qr_id || 0
    calibMarkerSize.value = p.marker_size || 0.058
    calibStreamType.value = p.stream_type || 'color'
  }
}

async function runCalibration() {
  if (!calibSceneId.value) { ElMessage.warning('请选择场景'); return }
  if (!calibPointName.value) { ElMessage.warning('请选择标定点'); return }
  calibrating.value = true; calibResult.value = null
  try {
    const res = await cameraApi.calibrate({
      camera_id: calibCameraId.value,
      arm: calibArm.value,
      qr_id: calibQrId.value,
      marker_size: calibMarkerSize.value,
      point_name: calibPointName.value,
      scene_id: calibSceneId.value,
      stream_type: calibStreamType.value,
    })
    calibResult.value = res.data || res
    ElMessage.success('标定完成')
    await reloadScenePoints()
  } catch (e) {
    ElMessage.error(e.message || '标定失败')
  } finally {
    calibrating.value = false
  }
}

// ========== 初始化 ==========

onMounted(() => {
  loadCameras()
  loadSceneList()
})
</script>

<style scoped>
.video-container { width: 100%; min-height: 360px; background: #050a10; border-radius: 8px; display: flex; align-items: center; justify-content: center; overflow: hidden; }
.video-frame { width: 100%; height: auto; display: block; }
.video-placeholder { text-align: center; }
.field-label { font-size: 12px; color: #9ca3af; margin-bottom: 4px; }
.section-title { font-size: 13px; color: #00d4ff; margin-bottom: 12px; padding-bottom: 6px; border-bottom: 1px solid #1e2d3d; }
.detect-result { margin-top: 10px; padding: 8px; background: #0d1a26; border: 1px solid #2a3a4a; border-radius: 6px; }
.detect-title { font-size: 12px; color: #00d4ff; margin-bottom: 6px; }
.point-data-panel { margin-top: 10px; padding: 10px; background: #0d1a26; border: 1px solid #2a3a4a; border-radius: 6px; }
</style>
