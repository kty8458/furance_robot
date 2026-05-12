<template>
  <div class="tech-page">
    <el-row :gutter="20">
      <el-col :span="24">
        <el-card class="tech-card" style="margin-bottom: 20px">
          <el-form :inline="true">
            <el-form-item label="选择机器人">
              <el-select v-model="selectedRobot" placeholder="选择机器人" style="width: 200px" @change="loadRobotStatus">
                <el-option v-for="robot in robots" :key="robot.id" :label="robot.name" :value="robot.id" />
              </el-select>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20">
      <el-col :span="12">
        <el-card class="tech-card">
          <template #header>
            <div class="tech-card-header">
              <el-icon><Position /></el-icon>
              <span style="margin-left: 8px">基础指令</span>
            </div>
          </template>

          <el-button type="primary" @click="handleHome" :disabled="!selectedRobot" style="width: 100%; margin-bottom: 10px">
            <el-icon><Location /></el-icon>
            归零
          </el-button>

          <el-button type="success" @click="showGrabDialog = true" :disabled="!selectedRobot" style="width: 100%; margin-bottom: 10px">
            <el-icon><Goods /></el-icon>
            抓取
          </el-button>

          <el-button type="warning" @click="showPlaceDialog = true" :disabled="!selectedRobot" style="width: 100%; margin-bottom: 10px">
            <el-icon><Goods /></el-icon>
            放置
          </el-button>

          <el-button :type="robotStatus?.enabled ? 'danger' : 'success'" @click="handleEnable" :disabled="!selectedRobot" style="width: 100%; margin-bottom: 10px">
            <el-icon><CircleCheck /></el-icon>
            {{ robotStatus?.enabled ? '禁用' : '使能' }}
          </el-button>

          <el-button type="info" @click="handleClearError" :disabled="!selectedRobot" style="width: 100%">
            <el-icon><CircleClose /></el-icon>
            清除错误
          </el-button>
        </el-card>

        <el-card class="tech-card" style="margin-top: 20px">
          <template #header>
            <div class="tech-card-header">
              <el-icon><Connection /></el-icon>
              <span style="margin-left: 8px">充电控制</span>
            </div>
          </template>

          <el-button type="success" @click="handleCharge('start')" :disabled="!selectedRobot" style="width: 100%; margin-bottom: 10px">
            <el-icon><SuccessFilled /></el-icon>
            开始充电
          </el-button>
          <el-button type="warning" @click="handleCharge('stop')" :disabled="!selectedRobot" style="width: 100%">
            <el-icon><SwitchButton /></el-icon>
            停止充电
          </el-button>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card class="tech-card">
          <template #header>
            <div class="tech-card-header">
              <el-icon><SwitchButton /></el-icon>
              <span style="margin-left: 8px">夹爪控制</span>
            </div>
          </template>

          <el-form :inline="true">
            <el-form-item label="手臂">
              <el-select v-model="gripperForm.arm" style="width: 100px">
                <el-option label="左" value="left" />
                <el-option label="右" value="right" />
              </el-select>
            </el-form-item>
            <el-form-item label="动作">
              <el-select v-model="gripperForm.action" style="width: 100px">
                <el-option label="打开" value="open" />
                <el-option label="闭合" value="close" />
              </el-select>
            </el-form-item>
            <el-form-item label="力(N)">
              <el-input-number v-model="gripperForm.force" :min="0" :max="100" style="width: 100px" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="handleGripper" :disabled="!selectedRobot">执行</el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <el-card class="tech-card" style="margin-top: 20px">
          <template #header>
            <div class="tech-card-header">
              <el-icon><Position /></el-icon>
              <span style="margin-left: 8px">升降控制</span>
            </div>
          </template>

          <el-form :inline="true">
            <el-form-item label="方向">
              <el-select v-model="liftForm.direction" style="width: 100px">
                <el-option label="上升" value="up" />
                <el-option label="下降" value="down" />
              </el-select>
            </el-form-item>
            <el-form-item label="高度(mm)">
              <el-input-number v-model="liftForm.height" :min="0" :max="1000" style="width: 100px" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="handleLift" :disabled="!selectedRobot">执行</el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <el-card class="tech-card" style="margin-top: 20px">
          <template #header>
            <div class="tech-card-header">
              <el-icon><MapLocation /></el-icon>
              <span style="margin-left: 8px">导航控制</span>
            </div>
          </template>

          <el-form :inline="true">
            <el-form-item label="地图">
              <el-select v-model="navigationForm.mapId" style="width: 150px" @change="loadWaypoints">
                <el-option v-for="map in maps" :key="map.id" :label="map.name" :value="map.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="导航点">
              <el-select v-model="navigationForm.waypointId" style="width: 150px">
                <el-option v-for="wp in waypoints" :key="wp.id" :label="wp.name" :value="wp.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="速度">
              <el-input-number v-model="navigationForm.speed" :min="0.1" :max="2" :step="0.1" style="width: 100px" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="handleMove" :disabled="!selectedRobot">移动</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
    </el-row>

    <!-- 抓取对话框 -->
    <el-dialog v-model="showGrabDialog" title="抓取" width="400px">
      <el-form>
        <el-form-item label="目标位置">
          <el-input v-model="grabForm.target" placeholder="输入目标位置" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showGrabDialog = false">取消</el-button>
        <el-button type="primary" @click="handleGrab">确认</el-button>
      </template>
    </el-dialog>

    <!-- 放置对话框 -->
    <el-dialog v-model="showPlaceDialog" title="放置" width="400px">
      <el-form>
        <el-form-item label="目标位置">
          <el-input v-model="placeForm.target" placeholder="输入目标位置" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showPlaceDialog = false">取消</el-button>
        <el-button type="primary" @click="handlePlace">确认</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Position, Goods, SwitchButton, Connection,
  Location, CircleCheck, CircleClose, SuccessFilled, MapLocation
} from '@element-plus/icons-vue'
import { robotApi } from '../api/robot'
import { navigationApi } from '../api/navigation'

const robots = ref([])
const selectedRobot = ref('')
const robotStatus = ref(null)
const maps = ref([])
const waypoints = ref([])

const showGrabDialog = ref(false)
const showPlaceDialog = ref(false)

const grabForm = ref({ target: '' })
const placeForm = ref({ target: '' })
const gripperForm = ref({ arm: 'left', action: 'open', force: 50 })
const liftForm = ref({ direction: 'up', height: 100 })
const navigationForm = ref({ mapId: '', waypointId: '', speed: 0.5 })

async function loadRobots() {
  try {
    const response = await robotApi.listRobots()
    robots.value = response.data.robots || []
    if (robots.value.length > 0 && !selectedRobot.value) {
      selectedRobot.value = robots.value[0].id
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

async function loadMaps() {
  try {
    const response = await navigationApi.getMaps()
    maps.value = response.data.maps || []
    if (maps.value.length > 0 && !navigationForm.value.mapId) {
      navigationForm.value.mapId = maps.value[0].id
      loadWaypoints()
    }
  } catch (error) {
    ElMessage.error('加载地图列表失败')
  }
}

async function loadWaypoints() {
  if (!navigationForm.value.mapId) return
  try {
    const response = await navigationApi.getWaypoints(navigationForm.value.mapId)
    waypoints.value = response.data.waypoints || []
  } catch (error) {
    ElMessage.error('加载导航点失败')
  }
}

async function handleHome() {
  try {
    await robotApi.home(selectedRobot.value)
    ElMessage.success('归零指令已发送')
  } catch (error) {
    ElMessage.error(error.response?.data?.message || '归零失败')
  }
}

async function handleGrab() {
  if (!grabForm.value.target) {
    ElMessage.warning('请输入目标位置')
    return
  }
  try {
    await robotApi.grab(selectedRobot.value, grabForm.value.target)
    ElMessage.success('抓取指令已发送')
    showGrabDialog.value = false
    grabForm.value.target = ''
  } catch (error) {
    ElMessage.error(error.response?.data?.message || '抓取失败')
  }
}

async function handlePlace() {
  if (!placeForm.value.target) {
    ElMessage.warning('请输入目标位置')
    return
  }
  try {
    await robotApi.place(selectedRobot.value, placeForm.value.target)
    ElMessage.success('放置指令已发送')
    showPlaceDialog.value = false
    placeForm.value.target = ''
  } catch (error) {
    ElMessage.error(error.response?.data?.message || '放置失败')
  }
}

async function handleGripper() {
  try {
    await robotApi.gripper(selectedRobot.value, gripperForm.value.arm, gripperForm.value.action, gripperForm.value.force)
    ElMessage.success('夹爪指令已发送')
  } catch (error) {
    ElMessage.error(error.response?.data?.message || '夹爪控制失败')
  }
}

async function handleLift() {
  try {
    await robotApi.lift(selectedRobot.value, liftForm.value.direction, liftForm.value.height)
    ElMessage.success('升降指令已发送')
  } catch (error) {
    ElMessage.error(error.response?.data?.message || '升降控制失败')
  }
}

async function handleCharge(action) {
  try {
    await robotApi.charge(selectedRobot.value, action)
    ElMessage.success(`充电${action === 'start' ? '开始' : '停止'}指令已发送`)
  } catch (error) {
    ElMessage.error(error.response?.data?.message || '充电控制失败')
  }
}

async function handleEnable() {
  try {
    await robotApi.enable(selectedRobot.value, !robotStatus.value?.enabled, false)
    ElMessage.success(`${!robotStatus.value?.enabled ? '使能' : '禁用'}成功`)
    loadRobotStatus()
  } catch (error) {
    ElMessage.error(error.response?.data?.message || '使能操作失败')
  }
}

async function handleClearError() {
  try {
    await robotApi.enable(selectedRobot.value, robotStatus.value?.enabled || true, true)
    ElMessage.success('错误已清除')
  } catch (error) {
    ElMessage.error(error.response?.data?.message || '清除错误失败')
  }
}

async function handleMove() {
  if (!navigationForm.value.mapId || !navigationForm.value.waypointId) {
    ElMessage.warning('请选择地图和导航点')
    return
  }
  try {
    await navigationApi.move(selectedRobot.value, navigationForm.value.mapId, navigationForm.value.waypointId, navigationForm.value.speed)
    ElMessage.success('移动指令已发送')
  } catch (error) {
    ElMessage.error(error.response?.data?.message || '移动失败')
  }
}

onMounted(() => {
  loadRobots()
  loadMaps()
})
</script>
