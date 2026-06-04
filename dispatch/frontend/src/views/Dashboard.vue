<template>
  <div>
    <h2 class="page-title">状态显示</h2>
    <el-row :gutter="20">
      <el-col :span="24" v-for="robot in robots" :key="robot.id">
        <el-card class="status-card" :class="{ offline: robot.status === 'offline' }">
          <template #header>
            <div class="card-header">
              <span>{{ robot.name }} ({{ robot.id }})</span>
              <el-tag :type="robot.status === 'offline' ? 'danger' : 'success'" size="small">
                {{ robot.status === 'offline' ? '离线' : '在线' }}
              </el-tag>
            </div>
          </template>
          <div v-if="robot.status_data" class="status-grid">
            <div class="status-item"><label>电量</label><span>{{ robot.status_data.battery }}%</span></div>
            <div class="status-item"><label>充电</label><span>{{ robot.status_data.charging ? '是' : '否' }}</span></div>
            <div class="status-item"><label>使能</label><span>{{ robot.status_data.enabled ? '已使能' : '未使能' }}</span></div>
            <div class="status-item"><label>任务</label><span>{{ robot.status_data.task_status }}</span></div>
            <div class="status-item"><label>位置</label><span>x:{{ robot.status_data.position?.x?.toFixed(2) }} y:{{ robot.status_data.position?.y?.toFixed(2) }}</span></div>
            <div class="status-item"><label>夹爪L</label><span>{{ robot.status_data.gripper?.left?.state }}</span></div>
            <div class="status-item"><label>夹爪R</label><span>{{ robot.status_data.gripper?.right?.state }}</span></div>
            <div class="status-item"><label>手臂L</label><span>{{ robot.status_data.arm?.left?.status }}</span></div>
            <div class="status-item"><label>手臂R</label><span>{{ robot.status_data.arm?.right?.status }}</span></div>
            <div class="status-item"><label>错误码</label><span>{{ robot.status_data.error_code }}</span></div>
            <div class="status-item"><label>头部偏转</label><span>{{ robot.status_data.motor?.head_pan_deg?.toFixed(2) ?? '--' }}°</span></div>
            <div class="status-item"><label>头部俯仰</label><span>{{ robot.status_data.motor?.head_tilt_deg?.toFixed(2) ?? '--' }}°</span></div>
            <div class="status-item"><label>升降高度</label><span>{{ robot.status_data.motor?.lift_height_cm?.toFixed(2) ?? '--' }}cm</span></div>
          </div>
          <div v-if="robot.status_data" class="arm-section">
            <div class="arm-side" v-if="robot.status_data.arm?.left">
              <div class="arm-title">左臂关节</div>
              <div class="joint-grid">
                <div class="joint-item" v-for="(v, i) in robot.status_data.arm.left.joint_angles" :key="'lj'+i">
                  <label>J{{ i+1 }}</label><span>{{ v?.toFixed(2) }}°</span>
                </div>
              </div>
              <div class="joint-grid" v-if="robot.status_data.arm.left.end_effector">
                <div class="joint-item"><label>x</label><span>{{ robot.status_data.arm.left.end_effector.x?.toFixed(1) }}</span></div>
                <div class="joint-item"><label>y</label><span>{{ robot.status_data.arm.left.end_effector.y?.toFixed(1) }}</span></div>
                <div class="joint-item"><label>z</label><span>{{ robot.status_data.arm.left.end_effector.z?.toFixed(1) }}</span></div>
                <div class="joint-item"><label>R</label><span>{{ robot.status_data.arm.left.end_effector.roll?.toFixed(1) }}</span></div>
                <div class="joint-item"><label>P</label><span>{{ robot.status_data.arm.left.end_effector.pitch?.toFixed(1) }}</span></div>
                <div class="joint-item"><label>Y</label><span>{{ robot.status_data.arm.left.end_effector.yaw?.toFixed(1) }}</span></div>
                <div class="joint-item"><label>参考坐标系</label><span>{{ robot.status_data.arm.left.coordinate_frame || 'base_link' }}</span></div>
              </div>
            </div>
            <div class="arm-side" v-if="robot.status_data.arm?.right">
              <div class="arm-title">右臂关节</div>
              <div class="joint-grid">
                <div class="joint-item" v-for="(v, i) in robot.status_data.arm.right.joint_angles" :key="'rj'+i">
                  <label>J{{ i+1 }}</label><span>{{ v?.toFixed(2) }}°</span>
                </div>
              </div>
              <div class="joint-grid" v-if="robot.status_data.arm.right.end_effector">
                <div class="joint-item"><label>x</label><span>{{ robot.status_data.arm.right.end_effector.x?.toFixed(1) }}</span></div>
                <div class="joint-item"><label>y</label><span>{{ robot.status_data.arm.right.end_effector.y?.toFixed(1) }}</span></div>
                <div class="joint-item"><label>z</label><span>{{ robot.status_data.arm.right.end_effector.z?.toFixed(1) }}</span></div>
                <div class="joint-item"><label>R</label><span>{{ robot.status_data.arm.right.end_effector.roll?.toFixed(1) }}</span></div>
                <div class="joint-item"><label>P</label><span>{{ robot.status_data.arm.right.end_effector.pitch?.toFixed(1) }}</span></div>
                <div class="joint-item"><label>Y</label><span>{{ robot.status_data.arm.right.end_effector.yaw?.toFixed(1) }}</span></div>
                <div class="joint-item"><label>参考坐标系</label><span>{{ robot.status_data.arm.right.coordinate_frame || 'base_link' }}</span></div>
              </div>
            </div>
          </div>
          <div v-else class="no-data">等待数据...</div>
        </el-card>
      </el-col>
    </el-row>

    <h3 style="margin-top: 24px;">制样机状态</h3>
    <el-card class="status-card">
      <div class="status-grid">
        <div class="status-item"><label>状态</label><span>{{ samplerData.status }}</span></div>
        <div class="status-item"><label>进度</label><span>{{ samplerData.progress }}%</span></div>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import api from '../api/index.js'

const robots = ref([])
const samplerData = ref({ status: 'idle', progress: 0 })
let timer = null

async function fetchData() {
  try {
    const r = await api.get('/dispatch/robots')
    robots.value = r.data?.robots || []
  } catch (e) { /* ignore */ }
  try {
    const s = await api.get('/dispatch/sampler/status')
    if (s.data) samplerData.value = s.data
  } catch (e) { /* ignore */ }
}

onMounted(() => {
  fetchData()
  timer = setInterval(fetchData, 5000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<style scoped>
.page-title { color: var(--tech-cyan); margin-bottom: 20px; }
.status-card { background: var(--tech-bg-card); border: 1px solid var(--tech-border); margin-bottom: 16px; }
.status-card.offline { opacity: 0.6; }
.card-header { display: flex; justify-content: space-between; align-items: center; color: var(--tech-text-bright); font-weight: 600; }
.status-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; }
.status-item label { display: block; font-size: 12px; color: var(--tech-text-muted); margin-bottom: 4px; }
.status-item span { color: var(--tech-text-bright); font-size: 15px; font-weight: 500; }
.no-data { color: var(--tech-text-muted); text-align: center; padding: 20px; }
.arm-section { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 16px; }
.arm-side { background: var(--tech-bg-card); border: 1px solid var(--tech-border); border-radius: 6px; padding: 12px; }
.arm-title { font-size: 13px; color: var(--tech-cyan); font-weight: 600; margin-bottom: 8px; }
.joint-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 6px; margin-bottom: 8px; }
.joint-item label { display: block; font-size: 10px; color: var(--tech-text-muted); }
.joint-item span { color: var(--tech-text-bright); font-size: 13px; font-family: 'Consolas', monospace; }
</style>
