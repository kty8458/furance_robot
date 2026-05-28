<template>
  <div>
    <h2 class="page-title">运行日志</h2>
    <el-row :gutter="16" style="margin-bottom: 16px;">
      <el-col :span="4">
        <el-select v-model="filterLevel" placeholder="级别" clearable @change="fetchLogs">
          <el-option label="info" value="info" />
          <el-option label="warn" value="warn" />
          <el-option label="error" value="error" />
        </el-select>
      </el-col>
      <el-col :span="4">
        <el-select v-model="filterSource" placeholder="来源" clearable @change="fetchLogs">
          <el-option label="控制系统" value="robot_control" />
          <el-option label="调度系统" value="dispatch" />
          <el-option label="制样机" value="sampler" />
        </el-select>
      </el-col>
    </el-row>

    <el-table :data="logs" class="tech-table" row-key="id" max-height="600">
      <el-table-column prop="level" label="级别" width="70">
        <template #default="{ row }">
          <el-tag :type="row.level === 'error' ? 'danger' : row.level === 'warn' ? 'warning' : 'info'" size="small">{{ row.level }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="source" label="来源" width="120" />
      <el-table-column prop="robot_id" label="机器人" width="100" />
      <el-table-column prop="message" label="消息" />
      <el-table-column prop="created_at" label="时间" width="180">
        <template #default="{ row }">{{ new Date(row.created_at * 1000).toLocaleString() }}</template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import api from '../api/index.js'

const logs = ref([])
const filterLevel = ref('')
const filterSource = ref('')
let timer = null

async function fetchLogs() {
  const params = {}
  if (filterLevel.value) params.level = filterLevel.value
  if (filterSource.value) params.source = filterSource.value
  try { const r = await api.get('/dispatch/logs', { params }); logs.value = r.data || [] } catch (e) {}
}

onMounted(() => {
  fetchLogs()
  timer = setInterval(fetchLogs, 5000)
})

onUnmounted(() => { if (timer) clearInterval(timer) })
</script>

<style scoped>
.page-title { color: #00d4ff; margin-bottom: 20px; }
.tech-table { background: #0a1628; }
</style>
