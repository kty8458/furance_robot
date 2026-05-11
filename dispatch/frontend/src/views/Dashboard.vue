<template>
  <div class="dashboard">
    <el-row :gutter="20">
      <el-col :span="12">
        <el-card>
          <template #header>
            <div class="card-header">
              <el-icon><Monitor /></el-icon>
              <span style="margin-left: 8px">机器人状态</span>
            </div>
          </template>

          <el-select v-model="selectedRobot" placeholder="选择机器人" style="width: 100%; margin-bottom: 15px" @change="loadRobotStatus">
            <el-option v-for="robot in robots" :key="robot.id" :label="robot.name" :value="robot.id" />
          </el-select>

          <el-descriptions v-if="robotStatus" :column="1" border>
            <el-descriptions-item label="位置">
              <div v-if="robotStatus.position">
                X: {{ robotStatus.position.x.toFixed(2) }}, Y: {{ robotStatus.position.y.toFixed(2) }}
              </div>
              <span v-else>--</span>
            </el-descriptions-item>
            <el-descriptions-item label="电量">
              <el-progress :percentage="robotStatus.battery || 0" :status="robotStatus.battery < 20 ? 'exception' : 'normal'" :stroke-width="8" style="width: 120px" />
            </el-descriptions-item>
            <el-descriptions-item label="任务状态">
              <el-tag :type="getStatusType(robotStatus.task_status)">
                {{ robotStatus.task_status || '空闲' }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="使能状态">
              <el-tag :type="robotStatus.enabled ? 'success' : 'danger'">
                {{ robotStatus.enabled ? '已使能' : '未使能' }}
              </el-tag>
            </el-descriptions-item>
          </el-descriptions>
          <el-empty v-else description="请选择机器人" />
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card>
          <template #header>
            <div class="card-header">
              <el-icon><Setting /></el-icon>
              <span style="margin-left: 8px">制样机状态</span>
            </div>
          </template>

          <el-descriptions v-if="samplerStatus" :column="1" border>
            <el-descriptions-item label="状态">
              <el-tag :type="getSamplerStatusType(samplerStatus.status)">
                {{ samplerStatus.status || '未知' }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="进度">
              <el-progress :percentage="samplerStatus.progress || 0" :stroke-width="8" />
            </el-descriptions-item>
          </el-descriptions>
          <el-empty v-else description="暂无数据" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Monitor, Setting } from '@element-plus/icons-vue'
import { robotApi } from '../api/robot'
import { samplerApi } from '../api/sampler'

const robots = ref([])
const selectedRobot = ref('')
const robotStatus = ref(null)
const samplerStatus = ref(null)
let refreshTimer = null

async function loadRobots() {
  try {
    const response = await robotApi.listRobots()
    robots.value = response.data.robots || []
    if (robots.value.length > 0 && !selectedRobot.value) {
      selectedRobot.value = robots.value[0].id
      loadRobotStatus()
    }
  } catch (error) {
    ElMessage.error('加载机器人列表失败')
  }
}

async function loadRobotStatus() {
  if (!selectedRobot.value) return
  try {
    const response = await robotApi.getStatus(selectedRobot.value)
    robotStatus.value = response.data
  } catch (error) {
    ElMessage.error('加载机器人状态失败')
  }
}

async function loadSamplerStatus() {
  try {
    const response = await samplerApi.getStatus()
    samplerStatus.value = response.data
  } catch (error) {
    // 静默失败
  }
}

function getStatusType(status) {
  switch (status) {
    case 'running': return 'warning'
    case 'completed': return 'success'
    case 'error': return 'danger'
    default: return 'info'
  }
}

function getSamplerStatusType(status) {
  switch (status) {
    case 'running': return 'success'
    case 'idle': return 'info'
    case 'error': return 'danger'
    case 'completed': return 'success'
    default: return 'info'
  }
}

onMounted(() => {
  loadRobots()
  loadSamplerStatus()
  refreshTimer = setInterval(() => {
    loadRobotStatus()
    loadSamplerStatus()
  }, 5000)
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})
</script>

<style scoped>
.dashboard {
  padding: 20px;
}

.card-header {
  display: flex;
  align-items: center;
}
</style>