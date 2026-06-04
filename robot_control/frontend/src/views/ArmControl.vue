<template>
  <div class="tech-page">
    <el-row :gutter="16">
      <!-- Left column: enable + upper body -->
      <el-col :xs="24" :sm="12" :md="10">
        <!-- Enable & arm status -->
        <el-card class="tech-card" style="margin-bottom: 16px">
          <template #header>
            <div class="tech-card-header">
              <el-icon><SetUp /></el-icon>
              <span style="margin-left: 8px">使能状态</span>
            </div>
          </template>
          <el-row :gutter="12">
            <el-col :span="12">
              <div class="enable-block">
                <div style="margin-bottom: 6px; font-size: 13px; color: #9ca3af">左臂</div>
                <el-tag :type="armEnabled('left') ? 'success' : 'danger'" size="large" style="width: 100%">
                  {{ armEnabled('left') ? '已使能' : '未使能' }}
                </el-tag>
              </div>
            </el-col>
            <el-col :span="12">
              <div class="enable-block">
                <div style="margin-bottom: 6px; font-size: 13px; color: #9ca3af">右臂</div>
                <el-tag :type="armEnabled('right') ? 'success' : 'danger'" size="large" style="width: 100%">
                  {{ armEnabled('right') ? '已使能' : '未使能' }}
                </el-tag>
              </div>
            </el-col>
          </el-row>
          <div style="margin-top: 10px; font-family: monospace; font-size: 12px; color: #9ca3af">
            左臂: {{ formatAngles(currentAngles('left')) }}<br>
            右臂: {{ formatAngles(currentAngles('right')) }}
          </div>
          <div style="margin-top: 8px; font-size: 12px; color: #6b7b8d">
            使能 / 停止请使用右下角悬浮按钮
          </div>
        </el-card>

        <!-- Upper body control -->
        <el-card class="tech-card">
          <template #header>
            <div class="tech-card-header">
              <el-icon><Operation /></el-icon>
              <span style="margin-left: 8px">上身控制</span>
            </div>
          </template>
          <div style="display: flex; flex-direction: column; gap: 10px">
            <!-- Waist -->
            <div>
              <div style="font-size: 12px; color: #9ca3af; margin-bottom: 4px">
                腰部升降: {{ upperBody.waist_angle }} (0-600)
              </div>
              <el-row :gutter="8" align="middle">
                <el-col :span="14">
                  <el-slider v-model="upperBody.waist_angle" :min="0" :max="600" :step="1" :show-tooltip="false" />
                </el-col>
                <el-col :span="4">
                  <el-input-number v-model="upperBody.waist_angle" :min="0" :max="600" size="small" controls-position="right" style="width: 100%" />
                </el-col>
                <el-col :span="4">
                  <span style="font-size: 11px; color: #6b7b8d">速度</span>
                  <el-input-number v-model="upperBody.waist_speed" :min="1" size="small" controls-position="right" style="width: 100%" />
                </el-col>
                <el-col :span="2">
                  <el-button size="small" type="primary" @click="handleWaistControl" :loading="upperBody.waistLoading">执行</el-button>
                </el-col>
              </el-row>
            </div>
            <!-- Head pan -->
            <div>
              <div style="font-size: 12px; color: #9ca3af; margin-bottom: 4px">
                头部偏转: {{ upperBody.ascend_pos }} (0-90°)
              </div>
              <el-row :gutter="8" align="middle">
                <el-col :span="14">
                  <el-slider v-model="upperBody.ascend_pos" :min="0" :max="90" :step="1" :show-tooltip="false" />
                </el-col>
                <el-col :span="4">
                  <el-input-number v-model="upperBody.ascend_pos" :min="0" :max="90" size="small" controls-position="right" style="width: 100%" />
                </el-col>
                <el-col :span="4">
                  <span style="font-size: 11px; color: #6b7b8d">速度</span>
                  <el-input-number v-model="upperBody.ascend_speed" :min="1" size="small" controls-position="right" style="width: 100%" />
                </el-col>
                <el-col :span="2">
                  <el-button size="small" type="primary" @click="handleAscendControl" :loading="upperBody.ascendLoading">执行</el-button>
                </el-col>
              </el-row>
            </div>
            <!-- Head tilt -->
            <div>
              <div style="font-size: 12px; color: #9ca3af; margin-bottom: 4px">
                头部俯仰: {{ upperBody.head_angle }} (0-35°)
              </div>
              <el-row :gutter="8" align="middle">
                <el-col :span="14">
                  <el-slider v-model="upperBody.head_angle" :min="0" :max="35" :step="0.5" :show-tooltip="false" />
                </el-col>
                <el-col :span="4">
                  <el-input-number v-model="upperBody.head_angle" :min="0" :max="35" :step="0.5" size="small" controls-position="right" style="width: 100%" />
                </el-col>
                <el-col :span="4">
                  <span style="font-size: 11px; color: #6b7b8d">速度</span>
                  <el-input-number v-model="upperBody.head_speed" :min="1" size="small" controls-position="right" style="width: 100%" />
                </el-col>
                <el-col :span="2">
                  <el-button size="small" type="primary" @click="handleHeadControl" :loading="upperBody.headLoading">执行</el-button>
                </el-col>
              </el-row>
            </div>
          </div>
        </el-card>
      </el-col>

      <!-- Right column: jog control -->
      <el-col :xs="24" :sm="12" :md="14">
        <el-card class="tech-card">
          <template #header>
            <div class="tech-card-header">
              <el-icon><Position /></el-icon>
              <span style="margin-left: 8px">点动控制</span>
            </div>
          </template>

          <!-- Arm + Mode + buttons -->
          <el-row :gutter="12" style="margin-bottom: 12px" align="middle">
            <el-col :span="4">
              <div style="font-size: 13px; color: #9ca3af; margin-bottom: 4px">手臂</div>
              <el-select v-model="jogForm.arm" style="width: 100%">
                <el-option label="左臂" value="left" />
                <el-option label="右臂" value="right" />
              </el-select>
            </el-col>
            <el-col :span="4">
              <div style="font-size: 13px; color: #9ca3af; margin-bottom: 4px">模式</div>
              <el-select v-model="jogForm.method" style="width: 100%">
                <el-option label="moveJ" value="moveJ" />
                <el-option label="moveP" value="movep" />
              </el-select>
            </el-col>
            <el-col :span="4" v-if="jogForm.method === 'movep'">
              <div style="font-size: 13px; color: #9ca3af; margin-bottom: 4px">坐标系</div>
              <el-select v-model="jogForm.coordinate" style="width: 100%">
                <el-option label="base_link" value="base_link" />
                <el-option label="world" value="world" />
                <el-option label="tool0" value="tool0" />
              </el-select>
            </el-col>
            <el-col :span="6" :offset="jogForm.method === 'movep' ? 6 : 10">
              <div style="display: flex; gap: 8px; align-items: flex-end; height: 100%; padding-bottom: 2px">
                <el-button size="small" @click="openTeachManager">示教管理</el-button>
                <el-button size="small" type="success" @click="showSaveDialog = true">点位保存</el-button>
              </div>
            </el-col>
          </el-row>

          <!-- moveJ step -->
          <el-row v-if="jogForm.method === 'moveJ'" :gutter="12" style="margin-bottom: 12px" align="middle">
            <el-col :span="16">
              <div style="font-size: 13px; color: #9ca3af; margin-bottom: 4px">
                步长: {{ jogForm.step.toFixed(3) }}°
              </div>
              <el-slider v-model="jogForm.step" :min="0.001" :max="5" :step="0.001" :show-tooltip="false" />
            </el-col>
            <el-col :span="8">
              <div style="font-size: 13px; color: #9ca3af; margin-bottom: 4px">手动输入</div>
              <el-input-number v-model="jogForm.step" :min="0.001" :max="5" :step="0.001" :precision="3" size="small" style="width: 100%" />
            </el-col>
          </el-row>

          <!-- moveP steps -->
          <template v-else>
            <el-row :gutter="12" style="margin-bottom: 8px" align="middle">
              <el-col :span="16">
                <div style="font-size: 13px; color: #9ca3af; margin-bottom: 4px">
                  坐标步长 (X/Y/Z): {{ jogForm.stepXyz.toFixed(1) }} mm
                </div>
                <el-slider v-model="jogForm.stepXyz" :min="1" :max="20" :step="0.1" :show-tooltip="false" />
              </el-col>
              <el-col :span="8">
                <div style="font-size: 13px; color: #9ca3af; margin-bottom: 4px">手动输入</div>
                <el-input-number v-model="jogForm.stepXyz" :min="1" :max="20" :step="0.1" :precision="1" size="small" style="width: 100%" />
              </el-col>
            </el-row>
            <el-row :gutter="12" style="margin-bottom: 12px" align="middle">
              <el-col :span="16">
                <div style="font-size: 13px; color: #9ca3af; margin-bottom: 4px">
                  角度步长 (R/P/Y): {{ jogForm.stepRpy.toFixed(2) }}°
                </div>
                <el-slider v-model="jogForm.stepRpy" :min="0.1" :max="2" :step="0.05" :show-tooltip="false" />
              </el-col>
              <el-col :span="8">
                <div style="font-size: 13px; color: #9ca3af; margin-bottom: 4px">手动输入</div>
                <el-input-number v-model="jogForm.stepRpy" :min="0.1" :max="2" :step="0.05" :precision="2" size="small" style="width: 100%" />
              </el-col>
            </el-row>
          </template>

          <!-- moveJ: 7 joint buttons -->
          <div v-if="jogForm.method === 'moveJ'" class="jog-grid">
            <div v-for="i in 7" :key="'jog'+i" class="jog-row">
              <span class="jog-label">J{{ i }}</span>
              <span class="jog-value">{{ currentAngles(jogForm.arm)[i-1]?.toFixed(4) ?? '0.0000' }}°</span>
              <el-button class="jog-btn jog-minus" size="large" @mousedown="startJog('joint', i-1, -1)" @mouseup="stopJog" @mouseleave="stopJog" @touchstart.prevent="startJog('joint', i-1, -1)" @touchend="stopJog">-</el-button>
              <el-button class="jog-btn jog-plus" size="large" type="primary" @mousedown="startJog('joint', i-1, 1)" @mouseup="stopJog" @mouseleave="stopJog" @touchstart.prevent="startJog('joint', i-1, 1)" @touchend="stopJog">+</el-button>
            </div>
          </div>

          <!-- moveP: 6 pose buttons -->
          <div v-else class="jog-grid">
            <div v-for="(label, idx) in poseLabels" :key="'pose'+idx" class="jog-row">
              <span class="jog-label">{{ label }}</span>
              <span class="jog-value">{{ currentPose(jogForm.arm)[idx]?.toFixed(4) ?? '0.0000' }}{{ idx < 3 ? '' : '°' }}</span>
              <el-button class="jog-btn jog-minus" size="large" @mousedown="startJog('pose', idx, -1)" @mouseup="stopJog" @mouseleave="stopJog" @touchstart.prevent="startJog('pose', idx, -1)" @touchend="stopJog">-</el-button>
              <el-button class="jog-btn jog-plus" size="large" type="primary" @mousedown="startJog('pose', idx, 1)" @mouseup="stopJog" @mouseleave="stopJog" @touchstart.prevent="startJog('pose', idx, 1)" @touchend="stopJog">+</el-button>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- Save Preset Dialog -->
    <el-dialog v-model="showSaveDialog" title="保存点位" width="360px">
      <el-form :model="saveForm" label-width="60px">
        <el-form-item label="名称">
          <el-input v-model="saveForm.name" placeholder="输入点位名称" />
        </el-form-item>
        <el-form-item label="手臂">
          <span style="color: #00d4ff">{{ jogForm.arm === 'left' ? '左臂' : '右臂' }}</span>
        </el-form-item>
        <el-form-item label="模式">
          <span style="color: #00d4ff">{{ jogForm.method }}</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showSaveDialog = false">取消</el-button>
        <el-button type="primary" @click="handleSavePreset" :loading="saving">保存</el-button>
      </template>
    </el-dialog>

    <!-- Teach Manager Dialog -->
    <el-dialog v-model="showTeachDialog" title="示教管理" width="1200px" top="2vh">
      <el-form :inline="true" size="small" style="margin-bottom: 12px">
        <el-form-item label="手臂筛选">
          <el-select v-model="teachFilter.arm" style="width: 120px" clearable placeholder="全部" @change="teachPage = 1">
            <el-option label="左臂" value="left" />
            <el-option label="右臂" value="right" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button size="small" @click="refreshTeachList">刷新</el-button>
        </el-form-item>
      </el-form>
      <el-table :data="pagedTeachList" border size="small">
        <el-table-column prop="name" label="名称" width="100" />
        <el-table-column label="手臂" width="70">
          <template #default="{ row }">
            <el-tag size="small" :type="row.arm === 'left' ? '' : 'info'">{{ row.arm === 'left' ? '左' : '右' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="数据" min-width="460">
          <template #default="{ row }">
            <div class="teach-data-block">
              <div class="teach-data-row">
                <span class="teach-data-label" v-for="i in 7" :key="'jl'+i">J{{ i }}</span>
              </div>
              <div class="teach-data-row">
                <span class="teach-data-val" v-for="(v, i) in row.joint_angles || []" :key="'jv'+i">{{ v?.toFixed(3) }}°</span>
                <span class="teach-data-val" v-if="!(row.joint_angles?.length)">--</span>
              </div>
            </div>
            <div class="teach-data-block">
              <div class="teach-data-row">
                <span class="teach-data-label">x</span>
                <span class="teach-data-label">y</span>
                <span class="teach-data-label">z</span>
                <span class="teach-data-label">R</span>
                <span class="teach-data-label">P</span>
                <span class="teach-data-label">Y</span>
                <span class="teach-data-label">坐标系</span>
              </div>
              <div class="teach-data-row">
                <span class="teach-data-val">{{ row.end_effector?.x?.toFixed(1) ?? '--' }}</span>
                <span class="teach-data-val">{{ row.end_effector?.y?.toFixed(1) ?? '--' }}</span>
                <span class="teach-data-val">{{ row.end_effector?.z?.toFixed(1) ?? '--' }}</span>
                <span class="teach-data-val">{{ row.end_effector?.roll?.toFixed(1) ?? '--' }}°</span>
                <span class="teach-data-val">{{ row.end_effector?.pitch?.toFixed(1) ?? '--' }}°</span>
                <span class="teach-data-val">{{ row.end_effector?.yaw?.toFixed(1) ?? '--' }}°</span>
                <span class="teach-data-val">{{ row.coordinate_frame || 'base_link' }}</span>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="运动模式" width="90">
          <template #default="{ row }">
            <el-tag size="small" type="success">{{ row.method || 'moveJ' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="210" fixed="right">
          <template #default="{ row }">
            <div style="display: flex; gap: 6px">
              <el-button size="small" type="primary" @click="handleTeachExec(row)">执行</el-button>
              <el-button size="small" type="warning" @click="handleTeachUpdate(row)">更新</el-button>
              <el-button size="small" type="danger" @click="handleTeachDelete(row)">删除</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
      <div style="margin-top: 12px; display: flex; justify-content: center">
        <el-pagination
          v-if="totalPages > 1"
          background
          layout="prev, pager, next"
          :page-size="10"
          :total="filteredTeachList.length"
          :current-page="teachPage"
          @current-change="teachPage = $event"
        />
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { armApi } from '../api/arm'
import { upperBodyApi } from '../api/upperBody'
import { useStatus } from '../composables/useStatus'
import { ElMessage, ElMessageBox } from 'element-plus'
import { SetUp, Operation, Position } from '@element-plus/icons-vue'

const { status } = useStatus()

const poseLabels = ['X', 'Y', 'Z', 'Roll', 'Pitch', 'Yaw']

const jogForm = ref({ arm: 'left', method: 'moveJ', coordinate: 'base_link', step: 0.05, stepXyz: 2, stepRpy: 0.5 })
const teachList = ref([])
const teachFilter = ref({ arm: '' })
const teachPage = ref(1)
const showSaveDialog = ref(false)
const showTeachDialog = ref(false)
const saveForm = ref({ name: '' })
const saving = ref(false)

const upperBody = ref({
  waist_angle: 300, waist_speed: 20, waistLoading: false,
  ascend_pos: 0, ascend_speed: 20, ascendLoading: false,
  head_angle: 15, head_speed: 10, headLoading: false,
})

let jogTimer = null
let jogPending = false
const JOG_INTERVAL = 150

watch(() => jogForm.value.method, (method) => {
  if (method === 'moveJ') jogForm.value.step = 0.05
})

onMounted(refreshTeachList)
onUnmounted(stopJog)

// -- Arm enable --
function armEnabled(side) {
  return status.value?.enabled ?? false
}

// -- Current joint angles --
function currentAngles(side) {
  const arm = status.value?.arm?.[side]
  if (arm?.joint_angles && Array.isArray(arm.joint_angles)) return arm.joint_angles
  return [0, 0, 0, 0, 0, 0, 0]
}

function currentPose(side) {
  const ee = status.value?.arm?.[side]?.end_effector
  if (ee) return [ee.x ?? 0, ee.y ?? 0, ee.z ?? 0, ee.roll ?? 0, ee.pitch ?? 0, ee.yaw ?? 0]
  return [0, 0, 0, 0, 0, 0]
}

// -- Jog control --
function startJog(mode, index, direction) {
  stopJog()
  sendJog(mode, index, direction)
  jogTimer = setInterval(() => { if (!jogPending) sendJog(mode, index, direction) }, JOG_INTERVAL)
}

function stopJog() {
  if (jogTimer) { clearInterval(jogTimer); jogTimer = null }
}

async function sendJog(mode, index, direction) {
  const side = jogForm.value.arm
  let step
  if (mode === 'joint') {
    step = jogForm.value.step * direction
  } else {
    const base = index < 3 ? jogForm.value.stepXyz : jogForm.value.stepRpy
    step = base * direction
  }
  jogPending = true
  try {
    if (mode === 'joint') {
      const angles = [...currentAngles(side)]
      angles[index] = round4(angles[index] + step)
      await armApi.move({ arm: side, method: 'moveJ', coordinate: jogForm.value.coordinate, joint_angles: angles })
    } else {
      const pose = [...currentPose(side)]
      pose[index] = round4(pose[index] + step)
      await armApi.move({ arm: side, method: jogForm.value.method, coordinate: jogForm.value.coordinate, position: { x: pose[0], y: pose[1], z: pose[2], roll: pose[3], pitch: pose[4], yaw: pose[5] } })
    }
  } catch { /* ignore */ } finally { jogPending = false }
}

function round4(v) { return Math.round(v * 10000) / 10000 }

// -- Teach management --
async function refreshTeachList() {
  try {
    const response = await armApi.teachList()
    const payload = response.data
    teachList.value = payload?.data || payload || []
  } catch (error) {
    ElMessage.error(error.message || '获取示教列表失败')
  }
}

const filteredTeachList = computed(() => {
  if (!teachFilter.value.arm) return teachList.value
  return teachList.value.filter(t => t.arm === teachFilter.value.arm)
})

const totalPages = computed(() => Math.ceil(filteredTeachList.value.length / 10))

const pagedTeachList = computed(() => {
  const start = (teachPage.value - 1) * 10
  return filteredTeachList.value.slice(start, start + 10)
})

function openTeachManager() {
  refreshTeachList()
  showTeachDialog.value = true
}

async function handleSavePreset() {
  if (!saveForm.value.name) {
    ElMessage.warning('请输入点位名称')
    return
  }
  saving.value = true
  try {
    await armApi.teachSave(jogForm.value.arm, saveForm.value.name, jogForm.value.method)
    ElMessage.success(`点位 "${saveForm.value.name}" 已保存`)
    saveForm.value.name = ''
    showSaveDialog.value = false
    refreshTeachList()
  } catch (error) {
    ElMessage.error(error.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function handleTeachExec(row) {
  try {
    await armApi.teachExec(row.arm, row.name, null)
    ElMessage.success(`执行指令已发送 (${row.method || 'moveJ'})`)
  } catch (error) {
    ElMessage.error(error.message || '执行失败')
  }
}

async function handleTeachUpdate(row) {
  try {
    await armApi.teachUpdate(row.arm, row.name, row.method || 'moveJ')
    ElMessage.success(`预设位 "${row.name}" 已更新`)
    refreshTeachList()
  } catch (error) {
    ElMessage.error(error.message || '更新失败')
  }
}

async function handleTeachDelete(row) {
  try {
    await ElMessageBox.confirm(`确定删除预设位 "${row.name}" 吗？`, '确认', { type: 'warning' })
    await armApi.teachDelete(row.name)
    ElMessage.success('删除成功')
    refreshTeachList()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(error.message || '删除失败')
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

// -- Upper body control --
async function handleWaistControl() {
  upperBody.value.waistLoading = true
  try {
    await upperBodyApi.waist({ waist_angle: upperBody.value.waist_angle, waist_speed: upperBody.value.waist_speed, reserve: 0 })
    ElMessage.success(`腰部已设至 ${upperBody.value.waist_angle}`)
  } catch (error) {
    ElMessage.error(error.message || '腰部控制失败')
  } finally { upperBody.value.waistLoading = false }
}

async function handleAscendControl() {
  upperBody.value.ascendLoading = true
  try {
    await upperBodyApi.ascend({ ascend_pos: upperBody.value.ascend_pos, ascend_speed: upperBody.value.ascend_speed, reserve: 0 })
    ElMessage.success(`头部偏转已设至 ${upperBody.value.ascend_pos}`)
  } catch (error) {
    ElMessage.error(error.message || '头部偏转失败')
  } finally { upperBody.value.ascendLoading = false }
}

async function handleHeadControl() {
  upperBody.value.headLoading = true
  try {
    await upperBodyApi.head({ head_angle: upperBody.value.head_angle, head_speed: upperBody.value.head_speed, reserve: 0 })
    ElMessage.success(`头部俯仰已设至 ${upperBody.value.head_angle}°`)
  } catch (error) {
    ElMessage.error(error.message || '头部俯仰失败')
  } finally { upperBody.value.headLoading = false }
}
</script>

<style scoped>
.enable-block { text-align: center; }
.jog-grid { display: flex; flex-direction: column; gap: 8px; }
.jog-row { display: flex; align-items: center; gap: 8px; }
.jog-label { width: 32px; font-weight: 600; font-size: 14px; color: #00d4ff; flex-shrink: 0; }
.jog-value { width: 110px; font-family: 'Consolas', 'Monaco', monospace; font-size: 13px; color: #e5e7eb; flex-shrink: 0; }
.jog-btn { flex: 1; height: 48px; font-size: 22px; font-weight: 700; border-radius: 8px; user-select: none; -webkit-user-select: none; touch-action: manipulation; }
.jog-minus { background: #1a2332; border-color: #ff3b5c44; color: #ff3b5c; }
.jog-minus:hover, .jog-minus:active { background: #2a1520; border-color: #ff3b5c; }
.jog-plus { background: #0d2818; border-color: #00ff8844; color: #00ff88; }
.jog-plus:hover, .jog-plus:active { background: #0d3820; border-color: #00ff88; }
.mono-sm { font-family: 'Consolas', 'Monaco', monospace; font-size: 11px; }
.teach-data-block { margin-bottom: 6px; }
.teach-data-block:last-child { margin-bottom: 0; }
.teach-data-row { display: grid; grid-template-columns: repeat(7, 1fr); gap: 2px; }
.teach-data-label { font-size: 10px; color: var(--tech-text-muted); text-align: center; }
.teach-data-val { font-size: 12px; color: var(--tech-text-bright); font-family: 'Consolas', monospace; text-align: center; }
</style>
