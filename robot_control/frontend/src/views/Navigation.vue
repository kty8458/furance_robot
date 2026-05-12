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

          <el-form :inline="true">
            <el-form-item label="选择地图">
              <el-select v-model="selectedMap" @change="handleMapChange" placeholder="请选择地图" style="width: 300px">
                <el-option v-for="map in maps" :key="map.id" :label="map.name" :value="map.id" />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button @click="refreshMaps">
                <el-icon><Refresh /></el-icon>
                刷新地图列表
              </el-button>
            </el-form-item>
          </el-form>

          <el-table :data="waypoints" border style="width: 100%; margin-bottom: 20px" @row-click="selectWaypoint" :row-class-name="getRowClassName">
            <el-table-column prop="id" label="ID" width="100" />
            <el-table-column prop="name" label="名称" />
            <el-table-column prop="x" label="X坐标" :formatter="formatCoord" />
            <el-table-column prop="y" label="Y坐标" :formatter="formatCoord" />
            <el-table-column prop="theta" label="角度" :formatter="formatTheta" />
          </el-table>

          <el-divider />

          <el-form :inline="true">
            <el-form-item label="目标点">
              <el-select v-model="moveForm.waypointId" placeholder="选择目标点" style="width: 300px">
                <el-option v-for="wp in waypoints" :key="wp.id" :label="wp.name" :value="wp.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="速度">
              <el-input-number v-model="moveForm.speed" :min="0.1" :max="2" :step="0.1" style="width: 120px" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="handleMove" :disabled="!selectedMap || !moveForm.waypointId">
                <el-icon><Promotion /></el-icon>
                移动到目标点
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { navigationApi } from '../api/navigation'
import { ElMessage } from 'element-plus'
import { MapLocation, Refresh, Promotion } from '@element-plus/icons-vue'

const maps = ref([])
const waypoints = ref([])
const selectedMap = ref(null)
const selectedWaypointId = ref(null)

const moveForm = ref({
  waypointId: null,
  speed: 0.5
})

onMounted(refreshMaps)

async function refreshMaps() {
  try {
    const response = await navigationApi.getMaps()
    maps.value = response.data || []
  } catch (error) {
    ElMessage.error(error.response?.data?.message || '获取地图列表失败')
  }
}

async function handleMapChange() {
  waypoints.value = []
  moveForm.value.waypointId = null
  if (selectedMap.value) {
    try {
      const response = await navigationApi.getWaypoints(selectedMap.value)
      waypoints.value = response.data || []
    } catch (error) {
      ElMessage.error(error.response?.data?.message || '获取航点列表失败')
    }
  }
}

function selectWaypoint(row) {
  selectedWaypointId.value = row.id
  moveForm.value.waypointId = row.id
}

function getRowClassName({ row }) {
  return row.id === selectedWaypointId.value ? 'selected-row' : ''
}

async function handleMove() {
  if (!selectedMap.value) {
    ElMessage.warning('请先选择地图')
    return
  }
  if (!moveForm.value.waypointId) {
    ElMessage.warning('请选择目标点')
    return
  }
  try {
    await navigationApi.move(selectedMap.value, moveForm.value.waypointId, moveForm.value.speed)
    ElMessage.success('移动指令已发送')
  } catch (error) {
    ElMessage.error(error.response?.data?.message || '移动失败')
  }
}

function formatCoord(row, column) {
  const val = row[column.property]
  return val !== undefined && val !== null ? val.toFixed(2) : '--'
}

function formatTheta(row) {
  return row.theta !== undefined && row.theta !== null ? row.theta.toFixed(2) + '°' : '--'
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
