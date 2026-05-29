<template>
  <div>
    <h2 class="page-title">制样机控制</h2>
    <el-card class="exec-card">
      <template #header><span>制样机状态</span></template>
      <div class="status-grid">
        <div class="status-item"><label>状态</label><span>{{ status.status }}</span></div>
        <div class="status-item"><label>进度</label><span>{{ status.progress }}%</span></div>
      </div>
    </el-card>
    <el-card class="exec-card" style="margin-top: 16px;">
      <template #header><span>控制</span></template>
      <el-button type="primary" @click="sendCommand('start')">启动</el-button>
      <el-button type="danger" @click="sendCommand('stop')">停止</el-button>
    </el-card>
    <el-card class="exec-card" style="margin-top: 16px;">
      <template #header><span>功能待定</span></template>
      <p style="color: var(--tech-text-muted);">制样机详细控制功能待后续确定</p>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api/index.js'

const status = ref({ status: 'idle', progress: 0 })

async function fetchStatus() {
  try { const r = await api.get('/dispatch/sampler/status'); if (r.data) status.value = r.data } catch (e) {}
}

async function sendCommand(cmd) {
  try {
    await api.post('/dispatch/sampler/command', { command: cmd, params: {} })
    ElMessage.success(`指令 ${cmd} 已发送`)
    fetchStatus()
  } catch (e) { ElMessage.error(e.message) }
}

onMounted(fetchStatus)
</script>

<style scoped>
.page-title { color: #00d4ff; margin-bottom: 20px; }
.exec-card { background: #0a1628; border: 1px solid #1a3a5c; }
.status-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.status-item label { display: block; font-size: 12px; color: var(--tech-text-muted); margin-bottom: 4px; }
.status-item span { color: var(--tech-text-bright); font-size: 15px; font-weight: 500; }
</style>
