<template>
  <div class="tech-page">
    <el-row :gutter="20">
      <el-col :span="24">
        <el-card class="tech-card">
          <template #header>
            <div class="tech-card-header">
              <el-icon><SetUp /></el-icon>
              <span style="margin-left: 8px">手臂运动控制</span>
            </div>
          </template>

          <el-form :inline="true" style="margin-bottom: 12px">
            <el-form-item label="手臂">
              <el-select v-model="moveForm.arm" style="width: 100px">
                <el-option label="左臂" value="left" />
                <el-option label="右臂" value="right" />
              </el-select>
            </el-form-item>
            <el-form-item label="运动方式">
              <el-select v-model="moveForm.method" style="width: 120px">
                <el-option label="moveJ" value="moveJ" />
                <el-option label="moveP" value="movep" />
                <el-option label="moveL" value="moveL" />
              </el-select>
            </el-form-item>
            <el-form-item label="坐标系">
              <el-select v-model="moveForm.coordinate" style="width: 120px">
                <el-option label="base_link" value="base_link" />
                <el-option label="tool" value="tool" />
              </el-select>
            </el-form-item>
          </el-form>

          <!-- Joint angles (for moveJ) -->
          <div v-if="moveForm.method === 'moveJ'" style="margin-bottom: 12px">
            <div style="color: #00d4ff; font-size: 13px; margin-bottom: 8px">关节角度 (7-DOF)</div>
            <el-form :inline="true">
              <el-form-item v-for="i in 7" :key="'j'+i" :label="'J'+i">
                <el-input-number v-model="moveForm.joints[i-1]" :step="0.1" style="width: 100px" />
              </el-form-item>
            </el-form>
          </div>

          <!-- End-effector pose (for moveP/moveL) -->
          <div v-if="moveForm.method !== 'moveJ'" style="margin-bottom: 12px">
            <div style="color: #00d4ff; font-size: 13px; margin-bottom: 8px">末端坐标</div>
            <el-form :inline="true">
              <el-form-item label="X"><el-input-number v-model="moveForm.eeX" :step="0.01" style="width: 110px" /></el-form-item>
              <el-form-item label="Y"><el-input-number v-model="moveForm.eeY" :step="0.01" style="width: 110px" /></el-form-item>
              <el-form-item label="Z"><el-input-number v-model="moveForm.eeZ" :step="0.01" style="width: 110px" /></el-form-item>
              <el-form-item label="Roll"><el-input-number v-model="moveForm.eeRoll" :step="0.01" style="width: 110px" /></el-form-item>
              <el-form-item label="Pitch"><el-input-number v-model="moveForm.eePitch" :step="0.01" style="width: 110px" /></el-form-item>
              <el-form-item label="Yaw"><el-input-number v-model="moveForm.eeYaw" :step="0.01" style="width: 110px" /></el-form-item>
            </el-form>
          </div>

          <el-button type="primary" @click="handleMove" style="width: 100%">
            <el-icon><VideoPlay /></el-icon>
            执行运动
          </el-button>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" style="margin-top: 20px">
      <el-col :span="24">
        <el-card class="tech-card">
          <template #header>
            <div class="tech-card-header">
              <el-icon><Files /></el-icon>
              <span style="margin-left: 8px">示教管理</span>
            </div>
          </template>

          <el-form :inline="true" style="margin-bottom: 12px">
            <el-form-item label="手臂">
              <el-select v-model="teachForm.arm" style="width: 100px">
                <el-option label="左臂" value="left" />
                <el-option label="右臂" value="right" />
              </el-select>
            </el-form-item>
            <el-form-item label="预设位名称">
              <el-input v-model="teachForm.name" placeholder="输入预设位名称" style="width: 180px" />
            </el-form-item>
            <el-form-item>
              <el-button type="success" @click="handleTeachSave">
                <el-icon><Plus /></el-icon> 保存
              </el-button>
            </el-form-item>
            <el-form-item>
              <el-button @click="refreshTeachList">
                <el-icon><Refresh /></el-icon> 刷新
              </el-button>
            </el-form-item>
          </el-form>

          <el-table :data="teachList" border style="width: 100%">
            <el-table-column prop="name" label="名称" width="100" />
            <el-table-column prop="arm" label="手臂" width="70">
              <template #default="{ row }">{{ row.arm === 'left' ? '左臂' : '右臂' }}</template>
            </el-table-column>
            <el-table-column label="关节角度" min-width="200">
              <template #default="{ row }">
                <span style="font-family: monospace; font-size: 12px">{{ formatAngles(row.joint_angles) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="末端坐标" min-width="160">
              <template #default="{ row }">
                <span style="font-family: monospace; font-size: 12px">{{ formatEE(row.end_effector) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="coordinate_frame" label="坐标系" width="100" />
            <el-table-column label="执行方式" width="130">
              <template #default="{ row }">
                <el-select v-model="row._execMethod" size="small" style="width: 110px">
                  <el-option label="moveJ" value="moveJ" />
                  <el-option label="moveP" value="movep" />
                  <el-option label="moveL" value="moveL" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="200">
              <template #default="{ row }">
                <el-button type="primary" size="small" @click="handleTeachExec(row)">
                  <el-icon><VideoPlay /></el-icon>
                </el-button>
                <el-button type="warning" size="small" @click="handleTeachUpdate(row)">
                  <el-icon><RefreshRight /></el-icon>
                </el-button>
                <el-button type="danger" size="small" @click="handleTeachDelete(row)">
                  <el-icon><Delete /></el-icon>
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { armApi } from '../api/arm'
import { ElMessage, ElMessageBox } from 'element-plus'
import { SetUp, Files, Plus, Refresh, VideoPlay, Delete, RefreshRight } from '@element-plus/icons-vue'

const moveForm = ref({
  arm: 'left',
  method: 'moveJ',
  coordinate: 'base_link',
  joints: [0, 0, 0, 0, 0, 0, 0],
  eeX: 0, eeY: 0, eeZ: 0, eeRoll: 0, eePitch: 0, eeYaw: 0,
})

const teachForm = ref({ arm: 'left', name: '' })
const teachList = ref([])

onMounted(refreshTeachList)

async function refreshTeachList() {
  try {
    const response = await armApi.teachList()
    const payload = response.data
    const list = payload?.data || payload || []
    teachList.value = list.map(item => ({ ...item, _execMethod: 'moveJ' }))
  } catch (error) {
    ElMessage.error(error.message || '获取示教列表失败')
  }
}

async function handleMove() {
  const params = {
    arm: moveForm.value.arm,
    method: moveForm.value.method,
    coordinate: moveForm.value.coordinate,
  }
  if (moveForm.value.method === 'moveJ') {
    params.joint_angles = moveForm.value.joints.slice()
  } else {
    params.position = {
      x: moveForm.value.eeX,
      y: moveForm.value.eeY,
      z: moveForm.value.eeZ,
      roll: moveForm.value.eeRoll,
      pitch: moveForm.value.eePitch,
      yaw: moveForm.value.eeYaw,
    }
  }
  try {
    await armApi.move(params)
    ElMessage.success('运动指令已发送')
  } catch (error) {
    ElMessage.error(error.message || '运动失败')
  }
}

async function handleTeachSave() {
  if (!teachForm.value.name) {
    ElMessage.warning('请输入预设位名称')
    return
  }
  try {
    await armApi.teachSave(teachForm.value.arm, teachForm.value.name)
    ElMessage.success('保存成功')
    teachForm.value.name = ''
    refreshTeachList()
  } catch (error) {
    ElMessage.error(error.message || '保存失败')
  }
}

async function handleTeachUpdate(row) {
  try {
    await armApi.teachUpdate(row.arm, row.name)
    ElMessage.success(`预设位 "${row.name}" 已更新为当前角度`)
    refreshTeachList()
  } catch (error) {
    ElMessage.error(error.message || '更新失败')
  }
}

async function handleTeachExec(row) {
  try {
    await armApi.teachExec(row.arm, row.name, row._execMethod)
    ElMessage.success(`执行指令已发送 (${row._execMethod})`)
  } catch (error) {
    ElMessage.error(error.message || '执行失败')
  }
}

async function handleTeachDelete(row) {
  try {
    await ElMessageBox.confirm(`确定删除预设位 "${row.name}" 吗？`, '确认', { type: 'warning' })
    await armApi.teachDelete(row.name)
    ElMessage.success('删除成功')
    refreshTeachList()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(error.message || '删除失败')
    }
  }
}

function formatAngles(angles) {
  if (!angles || !Array.isArray(angles)) return '--'
  return angles.map(a => a.toFixed(4) + '°').join(' ')
}

function formatEE(ee) {
  if (!ee) return '--'
  return `(${ee.x?.toFixed(3) ?? '?'}, ${ee.y?.toFixed(3) ?? '?'}, ${ee.z?.toFixed(3) ?? '?'})`
}
</script>
