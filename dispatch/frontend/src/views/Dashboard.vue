<template>
  <div>
    <h2 class="page-title">状态显示</h2>
    <el-row :gutter="20">
      <el-col :span="12" v-for="robot in robots" :key="robot.id">
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
.page-title { color: #00d4ff; margin-bottom: 20px; }
.status-card { background: #0a1628; border: 1px solid #1a3a5c; margin-bottom: 16px; }
.status-card.offline { opacity: 0.6; }
.card-header { display: flex; justify-content: space-between; align-items: center; color: #b0c4de; }
.status-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; }
.status-item label { display: block; font-size: 12px; color: #6b7b8d; }
.status-item span { color: #e0e8f0; font-size: 14px; }
.no-data { color: #6b7b8d; text-align: center; padding: 20px; }
</style>
