<template>
  <div class="tech-page">
    <el-row :gutter="20">
      <el-col :span="24">
        <el-card class="tech-card">
          <template #header>
            <div class="tech-card-header">
              <el-icon><MapLocation /></el-icon>
              <span style="margin-left: 8px">导航控制</span>
            </div>
          </template>

          <!-- Map selection & token -->
          <el-form :inline="true" style="margin-bottom: 16px">
            <el-form-item label="选择地图">
              <el-select v-model="mapName" @change="handleMapChange" placeholder="请选择地图" style="width: 240px">
                <el-option v-for="m in maps" :key="m.id || m" :label="m.name || m" :value="m.name || m" />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button @click="refreshMaps" :loading="mapsLoading">
                <el-icon><Refresh /></el-icon>
                刷新地图
              </el-button>
            </el-form-item>
            <el-form-item>
              <el-button @click="handleRefreshToken" :loading="tokenLoading" type="warning">
                <el-icon><Key /></el-icon>
                刷新Token
              </el-button>
            </el-form-item>
          </el-form>

          <!-- Task target table -->
          <el-table :data="taskTargets" border style="width: 100%; margin-bottom: 20px" @row-click="selectTarget" :row-class-name="getRowClassName">
            <el-table-column prop="type" label="类型" width="140">
              <template #default="{ row }">
                <el-tag :type="typeTagMap[row.type]" size="small">{{ typeLabelMap[row.type] }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="name" label="名称" />
            <el-table-column label="操作" width="180">
              <template #default="{ row }">
                <el-button type="primary" size="small" @click.stop="handleStart(row)" :disabled="taskRunning">
                  开始
                </el-button>
                <el-button type="danger" size="small" @click.stop="handleStop" :disabled="!taskRunning">
                  停止
                </el-button>
              </template>
            </el-table-column>
          </el-table>

          <el-divider />

          <!-- Task control -->
          <el-form :inline="true">
            <el-form-item>
              <el-button type="success" @click="handleRecharge" :disabled="!mapName">
                <el-icon><Lightning /></el-icon>
                自主回充
              </el-button>
            </el-form-item>
            <el-form-item v-if="taskRunning" style="margin-left: 20px">
              <el-tag type="warning" size="large">任务执行中...</el-tag>
            </el-form-item>
            <el-form-item v-else-if="taskFinished" style="margin-left: 20px">
              <el-tag type="success" size="large">任务已完成</el-tag>
            </el-form-item>
          </el-form>
        </el-card>

        <!-- 定距离/定角度移动控制 -->
        <el-card class="tech-card" style="margin-top: 16px">
          <template #header>
            <div class="tech-card-header">
              <el-icon><Position /></el-icon>
              <span style="margin-left: 8px">定距离/定角度移动控制</span>
            </div>
          </template>

          <el-form label-width="110px" label-position="left" size="small">
            <el-form-item label="模式">
              <el-radio-group v-model="mwpMode">
                <el-radio-button :value="1">定距离</el-radio-button>
                <el-radio-button :value="2">定角度</el-radio-button>
              </el-radio-group>
            </el-form-item>

            <el-row v-if="mwpMode === 1" :gutter="16">
              <el-col :span="8">
                <el-form-item label="线速度 (m/s)">
                  <el-input-number v-model="mwpLinearVelocity" :min="-0.5" :max="0.5" :step="0.05" :precision="2" controls-position="right" style="width: 100%" />
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="目标距离 (m)">
                  <el-input-number v-model="mwpTargetDistance" :min="0" :step="0.1" :precision="2" controls-position="right" style="width: 100%" />
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="侧偏角 (rad)">
                  <el-input-number v-model="mwpSlipAngle" :min="-2.14" :max="2.14" :step="0.1" :precision="2" controls-position="right" style="width: 100%" />
                </el-form-item>
              </el-col>
            </el-row>

            <el-row v-else :gutter="16">
              <el-col :span="12">
                <el-form-item label="角速度 (rad/s)">
                  <el-input-number v-model="mwpAngularVelocity" :min="-0.5" :max="0.5" :step="0.05" :precision="2" controls-position="right" style="width: 100%" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="目标角度 (rad)">
                  <el-input-number v-model="mwpTargetAngle" :min="0" :max="3.14" :step="0.1" :precision="2" controls-position="right" style="width: 100%" />
                </el-form-item>
              </el-col>
            </el-row>

            <el-form-item>
              <el-button type="primary" @click="handleMoveWithParams" :loading="mwpExecuting">
                执行移动
              </el-button>
              <el-button type="danger" @click="handleCancelMoveWithParams" style="margin-left: 8px">
                取消移动
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { navigationApi } from '../api/navigation'
import { ElMessage } from 'element-plus'
import { MapLocation, Refresh, Key, Lightning, Position } from '@element-plus/icons-vue'

const maps = ref([])
const mapName = ref(null)
const taskTargets = ref([])
const selectedTarget = ref(null)
const mapsLoading = ref(false)
const tokenLoading = ref(false)
const taskRunning = ref(false)
const taskFinished = ref(false)

// 定距离/定角度移动控制
const mwpMode = ref(1)  // 1=定距离, 2=定角度
const mwpLinearVelocity = ref(0.2)
const mwpSlipAngle = ref(0.0)
const mwpAngularVelocity = ref(0.2)
const mwpTargetDistance = ref(1.0)
const mwpTargetAngle = ref(0.0)
const mwpExecuting = ref(false)
let pollTimer = null

const typeLabelMap = {
  NavigationPointTask: '导航点',
  PlayGraphPathTask: '手动路径',
  PlayPathTask: '录制路径',
}
const typeTagMap = {
  NavigationPointTask: '',
  PlayGraphPathTask: 'warning',
  PlayPathTask: 'info',
}

onMounted(refreshMaps)
onUnmounted(() => { if (pollTimer) clearInterval(pollTimer) })

async function refreshMaps() {
  mapsLoading.value = true
  try {
    const response = await navigationApi.getMaps()
    const data = response.data || []
    maps.value = Array.isArray(data) ? data : []
  } catch (error) {
    ElMessage.error(error.message || '获取地图列表失败')
  } finally {
    mapsLoading.value = false
  }
}

async function handleRefreshToken() {
  tokenLoading.value = true
  try {
    await navigationApi.refreshToken()
    ElMessage.success('Token刷新成功')
  } catch (error) {
    ElMessage.error(error.message || 'Token刷新失败')
  } finally {
    tokenLoading.value = false
  }
}

async function handleMapChange() {
  taskTargets.value = []
  selectedTarget.value = null
  taskFinished.value = false
  if (!mapName.value) return

  try {
    const [posRes, graphRes, recordRes] = await Promise.all([
      navigationApi.getPositions(mapName.value),
      navigationApi.getGraphPaths(mapName.value),
      navigationApi.getRecordPaths(mapName.value),
    ])

    const positions = posRes.data || []
    const graphs = graphRes.data || []
    const records = recordRes.data || []

    const targets = []

    for (const p of Array.isArray(positions) ? positions : []) {
      targets.push({ type: 'NavigationPointTask', name: p.name })
    }
    for (const g of Array.isArray(graphs) ? graphs : []) {
      targets.push({ type: 'PlayGraphPathTask', name: g.name })
    }
    for (const r of Array.isArray(records) ? records : []) {
      targets.push({ type: 'PlayPathTask', name: r.name })
    }

    taskTargets.value = targets
  } catch (error) {
    ElMessage.error(error.message || '获取导航数据失败')
  }
}

function selectTarget(row) {
  selectedTarget.value = row
}

function getRowClassName({ row }) {
  return selectedTarget.value?.name === row.name && selectedTarget.value?.type === row.type ? 'selected-row' : ''
}

async function handleStart(row) {
  selectedTarget.value = row
  const name = mapName.value
  if (!name) {
    ElMessage.warning('请先选择地图')
    return
  }

  let task
  if (row.type === 'NavigationPointTask') {
    task = { name: 'NavigationPointTask', start_param: { map_name: name, position_name: row.name } }
  } else if (row.type === 'PlayGraphPathTask') {
    task = { name: 'PlayGraphPathTask', start_param: { map_name: name, graph_name: row.name } }
  } else {
    task = { name: 'PlayPathTask', start_param: { map_name: name, path_name: row.name } }
  }

  try {
    await navigationApi.startTask({ map_name: name, loop: false, tasks: [task] })
    ElMessage.success(`任务已启动: ${row.name}`)
    taskRunning.value = true
    taskFinished.value = false
    startPolling()
  } catch (error) {
    ElMessage.error(error.message || '任务启动失败')
  }
}

async function handleStop() {
  try {
    await navigationApi.stopTask()
    ElMessage.success('任务已停止')
    taskRunning.value = false
    stopPolling()
  } catch (error) {
    ElMessage.error(error.message || '停止任务失败')
  }
}

async function handleRecharge() {
  const name = mapName.value
  if (!name) {
    ElMessage.warning('请先选择地图')
    return
  }
  // Find a charging point if available
  const chargePoint = taskTargets.value.find(t => t.type === 'NavigationPointTask' && t.name?.includes('充电'))
  const pointName = chargePoint?.name || ''
  try {
    await navigationApi.recharge(name, pointName)
    ElMessage.success('回充指令已发送')
  } catch (error) {
    ElMessage.error(error.message || '回充指令失败')
  }
}

async function handleMoveWithParams() {
  mwpExecuting.value = true
  try {
    const body = {
      linear_velocity: mwpLinearVelocity.value,
      slip_angle: mwpSlipAngle.value,
      angular_velocity: mwpAngularVelocity.value,
      target_distance: mwpTargetDistance.value,
      target_angle: mwpTargetAngle.value,
      mode: mwpMode.value,
    }
    const res = await navigationApi.moveWithParams(body)
    ElMessage.success(res.data?.message || res.message || '移动指令已下发')
  } catch (error) {
    ElMessage.error(error.message || '移动指令失败')
  } finally {
    mwpExecuting.value = false
  }
}

async function handleCancelMoveWithParams() {
  try {
    await navigationApi.cancelMoveWithParams()
    ElMessage.success('取消指令已发送')
  } catch (error) {
    ElMessage.error(error.message || '取消失败')
  }
}

function startPolling() {
  stopPolling()
  pollTimer = setInterval(async () => {
    try {
      const statusRes = await navigationApi.getTaskStatus()
      // data=true 表示无任务在执行（即任务已完成或未启动）
      if (statusRes.data === true) {
        // 进一步查询队列状态以判断是成功完成还是出错
        try {
          const queueRes = await navigationApi.getQueueStatus()
          const msg = queueRes.message || ''
          if (msg.includes('不能到达')) {
            ElMessage.error(`导航失败: ${msg}`)
          } else {
            ElMessage.success('任务已完成')
          }
        } catch (e) {
          ElMessage.error(e.message || '导航失败')
        }
        taskRunning.value = false
        taskFinished.value = true
        stopPolling()
      }
    } catch {
      // ignore polling errors
    }
  }, 2000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}
</script>

<style scoped>
:deep(.selected-row) {
  background-color: #0d1f35 !important;
}
:deep(.el-table__body tr:hover) {
  background-color: #0d1f35 !important;
}
</style>
