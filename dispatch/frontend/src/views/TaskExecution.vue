<template>
  <div>
    <h2 class="page-title">任务执行</h2>

    <el-row :gutter="20">
      <el-col :span="8">
        <el-card class="exec-card">
          <template #header><span>手动触发</span></template>
          <el-select v-model="selectedTemplate" placeholder="选择任务模板" style="width: 100%">
            <el-option v-for="t in templates" :key="t.id" :label="t.name" :value="t.id" />
          </el-select>
          <el-button type="primary" style="margin-top: 12px; width: 100%" @click="executeTask" :loading="executing">
            执行任务
          </el-button>
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card class="exec-card">
          <template #header><span>L2监听</span></template>
          <el-tag type="info">L2监听待启用</el-tag>
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card class="exec-card">
          <template #header><span>快捷操作</span></template>
          <el-select v-model="quickRobot" placeholder="选择机器人" style="width: 100%">
            <el-option v-for="r in robots" :key="r.id" :label="r.name" :value="r.id" />
          </el-select>
          <el-select v-model="quickWorkflow" placeholder="选择工作流" style="width: 100%; margin-top: 8px">
            <el-option v-for="w in workflows" :key="w.name" :label="w.name" :value="w.name" />
          </el-select>
          <el-button type="warning" style="margin-top: 12px; width: 100%" @click="directCall">
            直接调用子任务
          </el-button>
        </el-card>
      </el-col>
    </el-row>

    <h3 style="margin-top: 24px; color: #00d4ff;">执行历史</h3>
    <el-table :data="executions" class="tech-table" row-key="id">
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="task_template_id" label="模板" width="120" />
      <el-table-column prop="trigger_type" label="触发" width="80" />
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="error_msg" label="错误信息" />
      <el-table-column label="操作" width="150">
        <template #default="{ row }">
          <el-button size="small" @click="viewExecution(row.id)">详情</el-button>
          <el-button v-if="row.status === 'running'" size="small" type="danger" @click="cancelExecution(row.id)">取消</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api/index.js'

const templates = ref([])
const robots = ref([])
const workflows = ref([])
const executions = ref([])
const selectedTemplate = ref('')
const quickRobot = ref('robot_001')
const quickWorkflow = ref('')
const executing = ref(false)

function statusType(s) {
  return { completed: 'success', running: 'warning', failed: 'danger', cancelled: 'info' }[s] || 'info'
}

async function fetchData() {
  try { const r = await api.get('/dispatch/tasks'); templates.value = r.data || [] } catch (e) {}
  try { const r = await api.get('/dispatch/robots'); robots.value = r.data?.robots || [] } catch (e) {}
  try { const r = await api.get('/dispatch/executions'); executions.value = r.data || [] } catch (e) {}
}

async function executeTask() {
  if (!selectedTemplate.value) { ElMessage.warning('请选择任务模板'); return }
  executing.value = true
  try {
    await api.post(`/dispatch/tasks/${selectedTemplate.value}/execute`, { trigger_type: 'manual' })
    ElMessage.success('任务已触发')
    fetchData()
  } catch (e) { ElMessage.error(e.message || '执行失败') }
  executing.value = false
}

async function directCall() {
  ElMessage.info('直接调用: ' + quickRobot.value + ' / ' + quickWorkflow.value)
}

async function cancelExecution(id) {
  try {
    await api.post(`/dispatch/executions/${id}/cancel`)
    ElMessage.success('已取消')
    fetchData()
  } catch (e) { ElMessage.error(e.message || '取消失败') }
}

async function viewExecution(id) {
  try {
    const r = await api.get(`/dispatch/executions/${id}`)
    ElMessage.info(JSON.stringify(r.data))
  } catch (e) {}
}

onMounted(fetchData)
</script>

<style scoped>
.page-title { color: #00d4ff; margin-bottom: 20px; }
.exec-card { background: #0a1628; border: 1px solid #1a3a5c; margin-bottom: 16px; }
.tech-table { background: #0a1628; }
</style>
