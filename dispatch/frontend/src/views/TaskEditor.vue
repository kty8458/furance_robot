<template>
  <div>
    <h2 class="page-title">任务编排</h2>
    <el-button type="primary" @click="openNew">新建任务模板</el-button>

    <el-table :data="templates" style="margin-top: 16px;" class="tech-table" row-key="id">
      <el-table-column prop="id" label="ID" width="150" />
      <el-table-column prop="name" label="名称" />
      <el-table-column prop="description" label="描述" />
      <el-table-column label="步骤数" width="80">
        <template #default="{ row }">
          {{ JSON.parse(row.steps_json || '[]').length }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="200">
        <template #default="{ row }">
          <el-button size="small" @click="editTemplate(row)">编辑</el-button>
          <el-button size="small" type="danger" @click="deleteTemplate(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="showDialog" :title="editingId ? '编辑任务' : '新建任务'" width="780px">
      <el-form :model="form" label-width="80px">
        <el-form-item label="ID">
          <el-input v-model="form.id" :disabled="!!editingId" />
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" />
        </el-form-item>
        <el-form-item label="步骤">
          <div v-for="(step, idx) in form.steps" :key="idx" class="step-row">
            <el-select v-model="step.type" style="width: 110px" @change="onTypeChange(step)">
              <el-option label="机器人" value="workflow" />
              <el-option label="制样机" value="sampler" />
              <el-option label="延时" value="delay" />
            </el-select>

            <!-- 机器人 workflow -->
            <template v-if="step.type === 'workflow'">
              <el-select
                v-model="step.config.robot_id"
                placeholder="选择机器人"
                style="width: 160px; margin-left: 8px;"
                @change="onRobotChange(step)"
              >
                <el-option
                  v-for="r in robots"
                  :key="r.id"
                  :label="`${r.name} (${r.id})`"
                  :value="r.id"
                />
              </el-select>
              <el-select
                v-model="step.config.workflow_name"
                placeholder="选择工作流"
                style="width: 200px; margin-left: 8px;"
                :loading="step._loading"
                :disabled="!step.config.robot_id"
                @change="onWorkflowChange(step)"
              >
                <el-option
                  v-for="wf in (workflowsByRobot[step.config.robot_id] || [])"
                  :key="wf.name"
                  :label="wf.description ? `${wf.name} - ${wf.description}` : wf.name"
                  :value="wf.name"
                />
              </el-select>
            </template>

            <!-- 制样机 -->
            <template v-else-if="step.type === 'sampler'">
              <el-select v-model="step.config.command" placeholder="指令" style="width: 200px; margin-left: 8px;">
                <el-option label="启动" value="start" />
                <el-option label="停止" value="stop" />
              </el-select>
            </template>

            <!-- 延时 -->
            <template v-else-if="step.type === 'delay'">
              <el-input-number
                v-model="step.config.seconds"
                :min="1"
                :max="3600"
                style="width: 160px; margin-left: 8px;"
              />
              <span style="margin-left: 8px; color: var(--tech-text-muted);">秒</span>
            </template>

            <el-button type="danger" size="small" @click="removeStep(idx)" circle style="margin-left: auto;">X</el-button>
          </div>
          <el-button size="small" @click="addStep">+ 添加步骤</el-button>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showDialog = false">取消</el-button>
        <el-button type="primary" @click="saveTemplate">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api/index.js'

const templates = ref([])
const robots = ref([])
const workflowsByRobot = ref({})
const showDialog = ref(false)
const editingId = ref(null)
const form = ref({ id: '', name: '', description: '', steps: [] })

let stepSeq = 0
function nextStepId() { stepSeq += 1; return `step_${Date.now()}_${stepSeq}` }

async function fetchTemplates() {
  try {
    const r = await api.get('/dispatch/tasks')
    templates.value = r.data || []
  } catch (e) { /* ignore */ }
}

async function fetchRobots() {
  try {
    const r = await api.get('/dispatch/robots')
    robots.value = r.data?.robots || []
  } catch (e) { /* ignore */ }
}

async function loadWorkflows(robotId) {
  if (!robotId || workflowsByRobot.value[robotId]) return
  try {
    const r = await api.get(`/dispatch/robots/${robotId}/workflows`)
    workflowsByRobot.value[robotId] = r.data || []
  } catch (e) {
    workflowsByRobot.value[robotId] = []
    ElMessage.warning(`获取机器人 ${robotId} 工作流失败`)
  }
}

function openNew() {
  editingId.value = null
  form.value = { id: '', name: '', description: '', steps: [] }
  showDialog.value = true
}

function addStep() {
  form.value.steps.push({
    id: nextStepId(),
    type: 'workflow',
    label: '',
    config: { robot_id: '', workflow_name: '' },
  })
}

function removeStep(idx) {
  form.value.steps.splice(idx, 1)
}

function onTypeChange(step) {
  if (step.type === 'workflow') step.config = { robot_id: '', workflow_name: '' }
  else if (step.type === 'sampler') step.config = { command: 'start' }
  else if (step.type === 'delay') step.config = { seconds: 5 }
  step.label = ''
}

async function onRobotChange(step) {
  step.config.workflow_name = ''
  step._loading = true
  await loadWorkflows(step.config.robot_id)
  step._loading = false
}

function onWorkflowChange(step) {
  const list = workflowsByRobot.value[step.config.robot_id] || []
  const wf = list.find(w => w.name === step.config.workflow_name)
  if (wf) step.label = wf.description || wf.name
}

async function editTemplate(row) {
  editingId.value = row.id
  const steps = JSON.parse(row.steps_json || '[]')
  form.value = {
    id: row.id,
    name: row.name,
    description: row.description || '',
    steps: steps.map(s => ({ ...s, config: s.config || {} })),
  }
  // preload workflows for any referenced robots
  const robotIds = [...new Set(steps.filter(s => s.type === 'workflow' && s.config?.robot_id).map(s => s.config.robot_id))]
  await Promise.all(robotIds.map(loadWorkflows))
  showDialog.value = true
}

async function saveTemplate() {
  for (const step of form.value.steps) {
    if (step.type === 'workflow' && (!step.config.robot_id || !step.config.workflow_name)) {
      ElMessage.warning('请为所有机器人步骤选择机器人和工作流')
      return
    }
    if (step.type === 'sampler' && !step.config.command) {
      ElMessage.warning('请为制样机步骤选择指令')
      return
    }
  }
  try {
    if (editingId.value) {
      await api.put(`/dispatch/tasks/${editingId.value}`, form.value)
    } else {
      await api.post('/dispatch/tasks', form.value)
    }
    showDialog.value = false
    editingId.value = null
    fetchTemplates()
    ElMessage.success('保存成功')
  } catch (e) {
    ElMessage.error(e.message || '保存失败')
  }
}

async function deleteTemplate(id) {
  try {
    await ElMessageBox.confirm('确认删除该模板?', '确认', { type: 'warning' })
    await api.delete(`/dispatch/tasks/${id}`)
    fetchTemplates()
    ElMessage.success('删除成功')
  } catch (e) { /* cancelled or error */ }
}

onMounted(() => {
  fetchTemplates()
  fetchRobots()
})
</script>

<style scoped>
.page-title { color: var(--tech-cyan); margin-bottom: 20px; }
.tech-table { background: var(--tech-bg-card); }
.step-row { display: flex; align-items: center; margin-bottom: 8px; }
</style>
