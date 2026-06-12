<template>
  <div class="tech-page">
    <!-- 顶部状态条 -->
    <div class="top-bar">
      <span :class="['status-dot', connected ? 'online' : 'offline']"></span>
      <el-tag :type="connected ? 'success' : 'danger'" size="small">{{ connected ? '在线' : '离线' }}</el-tag>
      <span style="margin-left: 16px; color: #6b7b8d; font-size: 13px">机器人状态监控</span>
    </div>

    <el-row :gutter="16">
      <!-- 底盘卡片 -->
      <el-col :xs="24" :sm="12" :md="8" style="margin-bottom: 16px">
        <el-card class="tech-card" :class="{ offline: !chassisOnline }">
          <template #header>
            <div class="card-header">
              <span>底盘</span>
              <el-tag :type="chassisOnline ? 'success' : 'danger'" size="small">{{ chassisOnline ? '在线' : '离线' }}</el-tag>
            </div>
          </template>
          <div class="card-body">
            <div class="field-row"><label>位置</label><span>{{ posText }}</span></div>
            <div class="field-row"><label>地图</label><span>{{ status?.current_map || '--' }}</span></div>
            <div class="field-row"><label>电量</label>
              <span>
                <el-progress :percentage="status?.battery || 0" :status="batteryStatus" :stroke-width="6" style="width: 100px; display: inline-block; vertical-align: middle" />
                <span style="margin-left: 8px">{{ status?.battery || 0 }}%</span>
              </span>
            </div>
            <div class="field-row"><label>充电</label>
              <el-tag :type="status?.charging ? 'success' : 'info'" size="small">{{ status?.charging ? '充电中' : '未充电' }}</el-tag>
            </div>
            <div class="field-row"><label>错误码</label>
              <span :class="status?.chassis_error ? 'text-danger' : 'text-ok'">{{ status?.chassis_error ? status.chassis_error : '正常' }}</span>
            </div>
            <div class="field-row"><label>状态</label>
              <el-tag :type="chassisStateTag" size="small">{{ chassisStateText }}</el-tag>
            </div>
          </div>
        </el-card>
      </el-col>

      <!-- 上身卡片 -->
      <el-col :xs="24" :sm="12" :md="8" style="margin-bottom: 16px">
        <el-card class="tech-card" :class="{ offline: !status?.upper_body_connected }">
          <template #header>
            <div class="card-header">
              <span>上身</span>
              <el-tag :type="status?.upper_body_connected ? 'success' : 'danger'" size="small">{{ status?.upper_body_connected ? '在线' : '离线' }}</el-tag>
            </div>
          </template>
          <div class="card-body">
            <div class="field-row"><label>头部偏转</label><span>{{ motorField('head_pan_deg') }}°</span></div>
            <div class="field-row"><label>头部俯仰</label><span>{{ motorField('head_tilt_deg') }}°</span></div>
            <div class="field-row"><label>升降高度</label><span>{{ liftHeightText }}</span></div>
          </div>
        </el-card>
      </el-col>

      <!-- 上肢卡片 -->
      <el-col :xs="24" :sm="12" :md="8" style="margin-bottom: 16px">
        <el-card class="tech-card" :class="{ offline: !armOnline }">
          <template #header>
            <div class="card-header">
              <span>上肢</span>
              <el-tag :type="armOnline ? 'success' : 'danger'" size="small">{{ armOnline ? '在线' : '离线' }}</el-tag>
            </div>
          </template>
          <div class="card-body">
            <div class="field-row"><label>使能</label>
              <el-tag :type="status?.enabled ? 'success' : 'danger'" size="small">{{ status?.enabled ? '已使能' : '未使能' }}</el-tag>
            </div>
            <div class="sub-title">左臂</div>
            <div class="field-row"><label>状态</label>
              <el-tag :type="armStatusTag('left')" size="small">{{ armStatusText('left') }}</el-tag>
            </div>
            <div class="field-row" v-if="armError('left') !== null"><label>错误码</label>
              <span :class="armError('left') ? 'text-danger' : 'text-ok'">{{ armError('left') || '正常' }}</span>
            </div>
            <div class="field-row"><label>关节</label><span class="mono">{{ jointText('left') }}</span></div>
            <div class="sub-title">右臂</div>
            <div class="field-row"><label>状态</label>
              <el-tag :type="armStatusTag('right')" size="small">{{ armStatusText('right') }}</el-tag>
            </div>
            <div class="field-row" v-if="armError('right') !== null"><label>错误码</label>
              <span :class="armError('right') ? 'text-danger' : 'text-ok'">{{ armError('right') || '正常' }}</span>
            </div>
            <div class="field-row"><label>关节</label><span class="mono">{{ jointText('right') }}</span></div>
          </div>
        </el-card>
      </el-col>

      <!-- 夹爪卡片 -->
      <el-col :xs="24" :sm="12" :md="8" style="margin-bottom: 16px">
        <el-card class="tech-card">
          <template #header>
            <div class="card-header">
              <span>夹爪</span>
            </div>
          </template>
          <div class="card-body">
            <div class="sub-title">左夹爪</div>
            <div class="field-row"><label>状态</label>
              <el-tag :type="gripperTag('left')" size="small">{{ gripperText('left') }}</el-tag>
            </div>
            <div class="field-row"><label>力度</label><span>{{ gripperField('left', 'force') }} N</span></div>
            <div class="field-row"><label>力矩</label><span>{{ gripperField('left', 'torque') }} Nm</span></div>
            <div class="field-row"><label>距离</label><span>{{ gripperField('left', 'distance') }} mm</span></div>
            <div class="field-row"><label>温度</label><span>{{ gripperField('left', 'temperature') }} °C</span></div>
            <div class="field-row"><label>连接</label>
              <span :class="gripperField('left', 'connected') ? 'text-ok' : 'text-danger'">{{ gripperField('left', 'connected') ? '已连接' : '未连接' }}</span>
            </div>
            <div class="sub-title">右夹爪</div>
            <div class="field-row"><label>状态</label>
              <el-tag :type="gripperTag('right')" size="small">{{ gripperText('right') }}</el-tag>
            </div>
            <div class="field-row"><label>力度</label><span>{{ gripperField('right', 'force') }} N</span></div>
            <div class="field-row"><label>力矩</label><span>{{ gripperField('right', 'torque') }} Nm</span></div>
            <div class="field-row"><label>距离</label><span>{{ gripperField('right', 'distance') }} mm</span></div>
            <div class="field-row"><label>温度</label><span>{{ gripperField('right', 'temperature') }} °C</span></div>
            <div class="field-row"><label>连接</label>
              <span :class="gripperField('right', 'connected') ? 'text-ok' : 'text-danger'">{{ gripperField('right', 'connected') ? '已连接' : '未连接' }}</span>
            </div>
          </div>
        </el-card>
      </el-col>

      <!-- 相机卡片 -->
      <el-col :xs="24" :sm="12" :md="8" style="margin-bottom: 16px">
        <el-card class="tech-card">
          <template #header>
            <div class="card-header">
              <span>相机</span>
              <el-button size="small" link @click="refreshCameras">刷新</el-button>
            </div>
          </template>
          <div class="card-body">
            <div v-for="cam in cameraStatus" :key="cam.id" class="field-row">
              <label>{{ cam.name }} ({{ cam.id }})</label>
              <span :class="cam.connected ? 'text-ok' : 'text-danger'">{{ cam.connected ? '已连接' : '未连接' }}</span>
            </div>
            <div v-if="!cameraStatus.length" class="field-row" style="color: #6b7b8d">点击刷新获取相机状态</div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useStatus } from '../composables/useStatus'

const { status, connected } = useStatus()

const cameraStatus = ref([])

// ---- 底盘 ----

const chassisOnline = computed(() => status.value?.source_status?.chassis ?? false)

const posText = computed(() => {
  const p = status.value?.position
  if (!p) return '--'
  return `X:${p.x?.toFixed(2) ?? '?'} Y:${p.y?.toFixed(2) ?? '?'} θ:${p.theta?.toFixed(2) ?? '?'}°`
})

const batteryStatus = computed(() => (status.value?.battery || 0) < 20 ? 'exception' : 'normal')

const chassisStateText = computed(() => {
  const map = { 0: '--', 1: '未运行', 2: '扫地图', 3: '导航启动', 4: '执行导航' }
  return map[status.value?.chassis_state] || '--'
})

const chassisStateTag = computed(() => {
  const s = status.value?.chassis_state
  if (s === 1) return 'info'
  if (s === 2) return 'warning'
  if (s === 3 || s === 4) return 'success'
  return ''
})

// ---- 上身 ----

function motorField(key) {
  if (!status.value?.motor) return '--'
  const v = status.value.motor[key]
  return v != null ? v.toFixed(2) : '--'
}

const liftHeightText = computed(() => {
  const h = status.value?.motor?.lift_height_cm
  return h != null ? `${(h * 10).toFixed(0)} mm` : '--'
})

// ---- 上肢 ----

const armOnline = computed(() => !!status.value?.arm && Object.keys(status.value.arm).length > 0)

function armStatusTag(side) {
  const s = status.value?.arm?.[side]?.status
  return s === 'idle' ? 'success' : 'warning'
}

function armStatusText(side) {
  return status.value?.arm?.[side]?.status || '--'
}

function armError(side) {
  return status.value?.arm?.[side]?.error_code ?? null
}

function jointText(side) {
  const angles = status.value?.arm?.[side]?.joint_angles
  if (!angles || !Array.isArray(angles)) return '--'
  return angles.map(a => a?.toFixed(4) + '°').join(', ')
}

// ---- 夹爪 ----

function gripperTag(side) {
  const s = status.value?.gripper?.[side]?.state
  return s === 'closed' ? 'success' : 'info'
}

function gripperText(side) {
  const s = status.value?.gripper?.[side]?.state
  return s === 'closed' ? '闭合' : '打开'
}

function gripperField(side, key) {
  const v = status.value?.gripper?.[side]?.[key]
  if (v == null) return '--'
  if (typeof v === 'number') return v.toFixed(1)
  return v
}

// ---- 相机 ----

async function refreshCameras() {
  try {
    const { cameraApi } = await import('../api/camera')
    const res = await cameraApi.list()
    cameraStatus.value = (res.data || []).map(c => ({
      id: c.id,
      name: c.name,
      connected: c.connected,
    }))
  } catch (e) {
    cameraStatus.value = []
  }
}

onMounted(refreshCameras)
</script>

<style scoped>
.top-bar { display: flex; align-items: center; margin-bottom: 16px; gap: 8px; }
.status-dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
.status-dot.online { background: #00ff88; box-shadow: 0 0 6px #00ff88; }
.status-dot.offline { background: #ff4444; box-shadow: 0 0 6px #ff4444; }

.tech-card { background: var(--tech-bg-card); border: 1px solid var(--tech-border); }
.tech-card.offline { opacity: 0.5; }

.card-header { display: flex; justify-content: space-between; align-items: center; color: var(--tech-text-bright); font-weight: 600; font-size: 14px; }

.card-body { display: flex; flex-direction: column; gap: 6px; }

.field-row { display: flex; justify-content: space-between; align-items: center; font-size: 13px; }
.field-row label { color: var(--tech-text-muted); font-size: 12px; min-width: 60px; }
.field-row span { color: var(--tech-text-bright); }

.sub-title { font-size: 12px; color: var(--tech-cyan); font-weight: 600; margin-top: 6px; margin-bottom: 2px; padding-bottom: 2px; border-bottom: 1px solid var(--tech-border); }

.mono { font-family: 'Consolas', monospace; font-size: 11px; }

.text-ok { color: #00ff88; }
.text-danger { color: #ff4444; }
</style>
