<template>
  <div class="tech-page">
    <el-row :gutter="16">
      <!-- Left column: status + teach management -->
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
                <el-button
                  :type="armEnabled('left') ? 'danger' : 'success'"
                  style="width: 100%; margin-top: 8px; height: 40px"
                  @click="toggleEnable('left')"
                >{{ armEnabled('left') ? '禁用' : '使能' }}</el-button>
              </div>
            </el-col>
            <el-col :span="12">
              <div class="enable-block">
                <div style="margin-bottom: 6px; font-size: 13px; color: #9ca3af">右臂</div>
                <el-tag :type="armEnabled('right') ? 'success' : 'danger'" size="large" style="width: 100%">
                  {{ armEnabled('right') ? '已使能' : '未使能' }}
                </el-tag>
                <el-button
                  :type="armEnabled('right') ? 'danger' : 'success'"
                  style="width: 100%; margin-top: 8px; height: 40px"
                  @click="toggleEnable('right')"
                >{{ armEnabled('right') ? '禁用' : '使能' }}</el-button>
              </div>
            </el-col>
          </el-row>
          <div style="margin-top: 10px; font-family: monospace; font-size: 12px; color: #9ca3af">
            左臂: {{ formatAngles(currentAngles('left')) }}<br>
            右臂: {{ formatAngles(currentAngles('right')) }}
          </div>
        </el-card>

        <!-- Teach management -->
        <el-card class="tech-card">
          <template #header>
            <div class="tech-card-header">
              <el-icon><Files /></el-icon>
              <span style="margin-left: 8px">示教管理</span>
            </div>
          </template>
          <el-form :inline="true" size="small" style="margin-bottom: 10px">
            <el-form-item label="手臂">
              <el-select v-model="teachForm.arm" style="width: 80px">
                <el-option label="左臂" value="left" />
                <el-option label="右臂" value="right" />
              </el-select>
            </el-form-item>
            <el-form-item label="名称">
              <el-input v-model="teachForm.name" placeholder="预设位" style="width: 120px" />
            </el-form-item>
            <el-form-item>
              <el-button type="success" size="small" @click="handleTeachSave">保存</el-button>
            </el-form-item>
            <el-form-item>
              <el-button size="small" @click="refreshTeachList">刷新</el-button>
            </el-form-item>
          </el-form>
          <el-table :data="teachList" border size="small" style="width: 100%" max-height="320">
            <el-table-column prop="name" label="名称" width="80" />
            <el-table-column prop="arm" label="臂" width="50">
              <template #default="{ row }">{{ row.arm === 'left' ? '左' : '右' }}</template>
            </el-table-column>
            <el-table-column label="角度" min-width="120">
              <template #default="{ row }">
                <span class="mono-sm">{{ formatAngles(row.joint_angles) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="末端" min-width="100">
              <template #default="{ row }">
                <span class="mono-sm">{{ formatEE(row.end_effector) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="160" fixed="right">
              <template #default="{ row }">
                <el-dropdown trigger="click" @command="cmd => handleTeachAction(row, cmd)">
                  <el-button type="primary" size="small">执行<el-icon><ArrowDown /></el-icon></el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="moveJ">moveJ (角度)</el-dropdown-item>
                      <el-dropdown-item command="movep">moveP (坐标)</el-dropdown-item>
                      <el-dropdown-item command="moveL">moveL (直线)</el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
                <el-button type="warning" size="small" @click="handleTeachUpdate(row)" style="margin-left: 4px">
                  更新
                </el-button>
                <el-button type="danger" size="small" @click="handleTeachDelete(row)" style="margin-left: 4px">
                  删
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <!-- Right column: jog control (tablet-friendly, large buttons) -->
      <el-col :xs="24" :sm="12" :md="14">
        <el-card class="tech-card">
          <template #header>
            <div class="tech-card-header">
              <el-icon><Position /></el-icon>
              <span style="margin-left: 8px">点动控制</span>
            </div>
          </template>

          <!-- Arm select + method + coordinate -->
          <el-row :gutter="12" style="margin-bottom: 12px" align="middle">
            <el-col :span="5">
              <div style="font-size: 13px; color: #9ca3af; margin-bottom: 4px">手臂</div>
              <el-select v-model="jogForm.arm" style="width: 100%">
                <el-option label="左臂" value="left" />
                <el-option label="右臂" value="right" />
              </el-select>
            </el-col>
            <el-col :span="5">
              <div style="font-size: 13px; color: #9ca3af; margin-bottom: 4px">模式</div>
              <el-select v-model="jogForm.method" style="width: 100%">
                <el-option label="moveJ" value="moveJ" />
                <el-option label="moveP" value="movep" />
              </el-select>
            </el-col>
            <el-col :span="5" v-if="jogForm.method === 'movep'">
              <div style="font-size: 13px; color: #9ca3af; margin-bottom: 4px">坐标系</div>
              <el-select v-model="jogForm.coordinate" style="width: 100%">
                <el-option label="base_link" value="base_link" />
                <el-option label="world" value="world" />
                <el-option label="tool0" value="tool0" />
              </el-select>
            </el-col>
            <el-col :span="9">
              <div style="font-size: 13px; color: #9ca3af; margin-bottom: 4px">
                步长: {{ jogForm.step.toFixed(3) }}{{ jogForm.method === 'moveJ' ? '°' : '' }}
              </div>
              <el-slider
                v-model="jogForm.step"
                :min="jogForm.method === 'moveJ' ? 0.001 : 0.0001"
                :max="jogForm.method === 'moveJ' ? 0.5 : 0.01"
                :step="jogForm.method === 'moveJ' ? 0.001 : 0.0001"
                :show-tooltip="false"
              />
            </el-col>
            <el-col :span="5">
              <div style="font-size: 13px; color: #9ca3af; margin-bottom: 4px">手动输入</div>
              <el-input-number
                v-model="jogForm.step"
                :min="jogForm.method === 'moveJ' ? 0.001 : 0.0001"
                :max="jogForm.method === 'moveJ' ? 0.5 : 0.01"
                :step="jogForm.method === 'moveJ' ? 0.001 : 0.0001"
                :precision="jogForm.method === 'moveJ' ? 3 : 4"
                size="small"
                style="width: 100%"
              />
            </el-col>
          </el-row>

          <!-- moveJ: 7 joint +/- buttons -->
          <div v-if="jogForm.method === 'moveJ'" class="jog-grid">
            <div v-for="i in 7" :key="'jog'+i" class="jog-row">
              <span class="jog-label">J{{ i }}</span>
              <span class="jog-value">{{ currentAngles(jogForm.arm)[i-1]?.toFixed(4) ?? '0.0000' }}°</span>
              <el-button
                class="jog-btn jog-minus"
                size="large"
                @mousedown="startJog('joint', i-1, -1)"
                @mouseup="stopJog"
                @mouseleave="stopJog"
                @touchstart.prevent="startJog('joint', i-1, -1)"
                @touchend="stopJog"
              >-</el-button>
              <el-button
                class="jog-btn jog-plus"
                size="large"
                type="primary"
                @mousedown="startJog('joint', i-1, 1)"
                @mouseup="stopJog"
                @mouseleave="stopJog"
                @touchstart.prevent="startJog('joint', i-1, 1)"
                @touchend="stopJog"
              >+</el-button>
            </div>
          </div>

          <!-- moveP: 6 pose +/- buttons (X Y Z R P Y) -->
          <div v-else class="jog-grid">
            <div v-for="(label, idx) in poseLabels" :key="'pose'+idx" class="jog-row">
              <span class="jog-label">{{ label }}</span>
              <span class="jog-value">{{ currentPose(jogForm.arm)[idx]?.toFixed(4) ?? '0.0000' }}{{ idx < 3 ? '' : '°' }}</span>
              <el-button
                class="jog-btn jog-minus"
                size="large"
                @mousedown="startJog('pose', idx, -1)"
                @mouseup="stopJog"
                @mouseleave="stopJog"
                @touchstart.prevent="startJog('pose', idx, -1)"
                @touchend="stopJog"
              >-</el-button>
              <el-button
                class="jog-btn jog-plus"
                size="large"
                type="primary"
                @mousedown="startJog('pose', idx, 1)"
                @mouseup="stopJog"
                @mouseleave="stopJog"
                @touchstart.prevent="startJog('pose', idx, 1)"
                @touchend="stopJog"
              >+</el-button>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { armApi } from '../api/arm'
import { useStatus } from '../composables/useStatus'
import { ElMessage, ElMessageBox } from 'element-plus'
import { SetUp, Files, Position, ArrowDown } from '@element-plus/icons-vue'
import { robotApi } from '../api/robot'

const { status } = useStatus()

const poseLabels = ['X', 'Y', 'Z', 'Roll', 'Pitch', 'Yaw']

const jogForm = ref({ arm: 'left', method: 'moveJ', coordinate: 'base_link', step: 0.05 })
const teachForm = ref({ arm: 'left', name: '' })
const teachList = ref([])

let jogTimer = null
let jogPending = false
const JOG_INTERVAL = 150

// Reset step when method changes
watch(() => jogForm.value.method, (method) => {
  if (method === 'moveJ') jogForm.value.step = 0.05
  else jogForm.value.step = 0.001
})

onMounted(refreshTeachList)
onUnmounted(stopJog)

// -- Arm enable --

function armEnabled(side) {
  return status.value?.enabled ?? false
}

async function toggleEnable(side) {
  try {
    const newEnabled = !status.value?.enabled
    await robotApi.enable(newEnabled, false)
    ElMessage.success(newEnabled ? '已使能' : '已禁用')
  } catch (error) {
    ElMessage.error(error.message || '使能操作失败')
  }
}

// -- Current joint angles from status --

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

// -- Jog control with rate limiting --

function startJog(mode, index, direction) {
  stopJog()
  sendJog(mode, index, direction)
  jogTimer = setInterval(() => {
    if (!jogPending) sendJog(mode, index, direction)
  }, JOG_INTERVAL)
}

function stopJog() {
  if (jogTimer) { clearInterval(jogTimer); jogTimer = null }
}

async function sendJog(mode, index, direction) {
  const side = jogForm.value.arm
  const step = jogForm.value.step * direction
  jogPending = true
  try {
    if (mode === 'joint') {
      const angles = [...currentAngles(side)]
      angles[index] = round4(angles[index] + step)
      await armApi.move({
        arm: side,
        method: 'moveJ',
        coordinate: jogForm.value.coordinate,
        joint_angles: angles,
      })
    } else {
      const pose = [...currentPose(side)]
      pose[index] = round4(pose[index] + step)
      await armApi.move({
        arm: side,
        method: jogForm.value.method,
        coordinate: jogForm.value.coordinate,
        position: { x: pose[0], y: pose[1], z: pose[2], roll: pose[3], pitch: pose[4], yaw: pose[5] },
      })
    }
  } catch {
    // Silently ignore jog errors
  } finally {
    jogPending = false
  }
}

function round4(v) { return Math.round(v * 10000) / 10000 }

// -- Teach management --

onMounted(refreshTeachList)

async function refreshTeachList() {
  try {
    const response = await armApi.teachList()
    const payload = response.data
    teachList.value = payload?.data || payload || []
  } catch (error) {
    ElMessage.error(error.message || '获取示教列表失败')
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
    ElMessage.success(`预设位 "${row.name}" 已更新`)
    refreshTeachList()
  } catch (error) {
    ElMessage.error(error.message || '更新失败')
  }
}

async function handleTeachAction(row, method) {
  try {
    await armApi.teachExec(row.arm, row.name, method)
    ElMessage.success(`执行指令已发送 (${method})`)
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
</script>

<style scoped>
.enable-block {
  text-align: center;
}
.jog-grid {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.jog-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.jog-label {
  width: 32px;
  font-weight: 600;
  font-size: 14px;
  color: #00d4ff;
  flex-shrink: 0;
}
.jog-value {
  width: 110px;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
  color: #e5e7eb;
  flex-shrink: 0;
}
.jog-btn {
  flex: 1;
  height: 48px;
  font-size: 22px;
  font-weight: 700;
  border-radius: 8px;
  user-select: none;
  -webkit-user-select: none;
  touch-action: manipulation;
}
.jog-minus {
  background: #1a2332;
  border-color: #ff3b5c44;
  color: #ff3b5c;
}
.jog-minus:hover, .jog-minus:active {
  background: #2a1520;
  border-color: #ff3b5c;
}
.jog-plus {
  background: #0d2818;
  border-color: #00ff8844;
  color: #00ff88;
}
.jog-plus:hover, .jog-plus:active {
  background: #0d3820;
  border-color: #00ff88;
}
.mono-sm {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 11px;
}
</style>
