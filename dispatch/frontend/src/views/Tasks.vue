<template>
  <div class="tasks">
    <el-row :gutter="20">
      <el-col :span="24">
        <el-card style="margin-bottom: 20px">
          <template #header>
            <div class="card-header">
              <el-icon><Document /></el-icon>
              <span style="margin-left: 8px">任务模板</span>
            </div>
          </template>

          <el-table :data="taskTemplates" style="width: 100%">
            <el-table-column prop="id" label="ID" width="80" />
            <el-table-column prop="name" label="名称" />
            <el-table-column prop="description" label="描述" />
            <el-table-column label="操作" width="150">
              <template #default="scope">
                <el-button type="primary" size="small" @click="showExecuteDialog(scope.row)">执行</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20">
      <el-col :span="24">
        <el-card>
          <template #header>
            <div class="card-header">
              <el-icon><List /></el-icon>
              <span style="margin-left: 8px">执行历史</span>
              <el-button type="primary" size="small" style="margin-left: auto" @click="loadExecutions">刷新</el-button>
            </div>
          </template>

          <el-table :data="executions" style="width: 100%">
            <el-table-column prop="id" label="ID" width="80" />
            <el-table-column prop="template_name" label="任务模板" />
            <el-table-column prop="robot_id" label="机器人" width="120" />
            <el-table-column label="状态" width="100">
              <template #default="scope">
                <el-tag :type="getStatusType(scope.row.status)">
                  {{ scope.row.status }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="start_time" label="开始时间" />
            <el-table-column prop="end_time" label="结束时间" />
            <el-table-column label="操作" width="200">
              <template #default="scope">
                <el-button type="info" size="small" @click="showDetailDialog(scope.row)">详情</el-button>
                <el-button v-if="scope.row.status === 'running'" type="danger" size="small" @click="handleCancel(scope.row)">取消</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <!-- 执行任务对话框 -->
    <el-dialog v-model="showExecute" title="执行任务" width="400px">
      <el-form>
        <el-form-item label="任务模板">
          <el-input :value="selectedTemplate?.name" disabled />
        </el-form-item>
        <el-form-item label="选择机器人">
          <el-select v-model="executeForm.robotId" placeholder="选择机器人" style="width: 100%">
            <el-option v-for="robot in robots" :key="robot.id" :label="robot.name" :value="robot.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showExecute = false">取消</el-button>
        <el-button type="primary" @click="handleExecute">确认执行</el-button>
      </template>
    </el-dialog>

    <!-- 任务详情对话框 -->
    <el-dialog v-model="showDetail" title="任务详情" width="600px">
      <el-descriptions :column="1" border v-if="selectedExecution">
        <el-descriptions-item label="任务ID">{{ selectedExecution.id }}</el-descriptions-item>
        <el-descriptions-item label="任务模板">{{ selectedExecution.template_name }}</el-descriptions-item>
        <el-descriptions-item label="机器人">{{ selectedExecution.robot_id }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="getStatusType(selectedExecution.status)">{{ selectedExecution.status }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="开始时间">{{ selectedExecution.start_time }}</el-descriptions-item>
        <el-descriptions-item label="结束时间">{{ selectedExecution.end_time || '--' }}</el-descriptions-item>
        <el-descriptions-item label="错误信息">{{ selectedExecution.error || '--' }}</el-descriptions-item>
      </el-descriptions>
      <div v-if="selectedExecution?.steps" style="margin-top: 20px">
        <h4>执行步骤</h4>
        <el-timeline>
          <el-timeline-item v-for="(step, index) in selectedExecution.steps" :key="index" :timestamp="step.time" :type="getStepType(step.status)">
            {{ step.name }} - {{ step.status }}
          </el-timeline-item>
        </el-timeline>
      </div>
      <template #footer>
        <el-button @click="showDetail = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Document, List } from '@element-plus/icons-vue'
import { taskApi } from '../api/task'
import { robotApi } from '../api/robot'

const taskTemplates = ref([])
const executions = ref([])
const robots = ref([])

const showExecute = ref(false)
const showDetail = ref(false)
const selectedTemplate = ref(null)
const selectedExecution = ref(null)
const executeForm = ref({ robotId: '' })

async function loadTaskTemplates() {
  try {
    const response = await taskApi.listTemplates()
    taskTemplates.value = response.data.templates || []
  } catch (error) {
    ElMessage.error('加载任务模板失败')
  }
}

async function loadExecutions() {
  try {
    const response = await taskApi.listExecutions()
    executions.value = response.data.executions || []
  } catch (error) {
    ElMessage.error('加载执行历史失败')
  }
}

async function loadRobots() {
  try {
    const response = await robotApi.listRobots()
    robots.value = response.data.robots || []
  } catch (error) {
    ElMessage.error('加载机器人列表失败')
  }
}

function showExecuteDialog(template) {
  selectedTemplate.value = template
  executeForm.value.robotId = ''
  showExecute.value = true
}

async function handleExecute() {
  if (!executeForm.value.robotId) {
    ElMessage.warning('请选择机器人')
    return
  }
  try {
    await taskApi.executeTask(selectedTemplate.value.id, executeForm.value.robotId)
    ElMessage.success('任务已开始执行')
    showExecute.value = false
    loadExecutions()
  } catch (error) {
    ElMessage.error(error.response?.data?.message || '任务执行失败')
  }
}

async function showDetailDialog(execution) {
  try {
    const response = await taskApi.getExecution(execution.id)
    selectedExecution.value = response.data
    showDetail.value = true
  } catch (error) {
    ElMessage.error('加载任务详情失败')
  }
}

async function handleCancel(execution) {
  try {
    await ElMessageBox.confirm('确定要取消这个任务吗?', '确认', {
      type: 'warning'
    })
    await taskApi.cancelExecution(execution.id)
    ElMessage.success('任务已取消')
    loadExecutions()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(error.response?.data?.message || '取消任务失败')
    }
  }
}

function getStatusType(status) {
  switch (status) {
    case 'running': return 'warning'
    case 'completed': return 'success'
    case 'error': return 'danger'
    case 'cancelled': return 'info'
    default: return 'info'
  }
}

function getStepType(status) {
  switch (status) {
    case 'completed': return 'success'
    case 'running': return 'primary'
    case 'error': return 'danger'
    default: return 'info'
  }
}

onMounted(() => {
  loadTaskTemplates()
  loadExecutions()
  loadRobots()
})
</script>

<style scoped>
.tasks {
  padding: 20px;
}

.card-header {
  display: flex;
  align-items: center;
}
</style>