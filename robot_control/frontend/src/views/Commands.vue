<template>
  <div class="tech-page">
    <el-row :gutter="20">
      <el-col :span="12">
        <el-card class="tech-card">
          <template #header>
            <div class="tech-card-header">
              <el-icon><Position /></el-icon>
              <span style="margin-left: 8px">基础指令</span>
            </div>
          </template>

          <el-button type="primary" @click="handleHome" style="width: 100%; margin-bottom: 10px; height: 44px; font-size: 14px">
            <el-icon><Location /></el-icon>
            归零
          </el-button>

          <el-button type="success" @click="showGrabDialog = true" style="width: 100%; margin-bottom: 10px; height: 44px; font-size: 14px">
            <el-icon><Goods /></el-icon>
            抓取
          </el-button>

          <el-button type="warning" @click="showPlaceDialog = true" style="width: 100%; margin-bottom: 10px; height: 44px; font-size: 14px">
            <el-icon><Goods /></el-icon>
            放置
          </el-button>

          <el-button :type="status?.enabled ? 'danger' : 'success'" @click="handleEnable" style="width: 100%; margin-bottom: 10px; height: 44px; font-size: 14px">
            <el-icon><CircleCheck /></el-icon>
            {{ status?.enabled ? '禁用' : '使能' }}
          </el-button>

          <el-button type="info" @click="handleClearError" style="width: 100%; height: 44px; font-size: 14px">
            <el-icon><CircleClose /></el-icon>
            清除错误
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
              <el-button type="primary" @click="handleGripper">执行</el-button>
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
              <el-button type="primary" @click="handleLift">执行</el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <el-card class="tech-card" style="margin-top: 20px">
          <template #header>
            <div class="tech-card-header">
              <el-icon><Connection /></el-icon>
              <span style="margin-left: 8px">充电控制</span>
            </div>
          </template>

          <el-button type="success" @click="handleCharge('start')" style="width: 100%; margin-bottom: 10px; height: 44px; font-size: 14px">
            <el-icon><SuccessFilled /></el-icon>
            开始充电
          </el-button>
          <el-button type="warning" @click="handleCharge('stop')" style="width: 100%; height: 44px; font-size: 14px">
            <el-icon><SwitchButton /></el-icon>
            停止充电
          </el-button>
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
import { ref } from 'vue'
import { robotApi } from '../api/robot'
import { useStatus } from '../composables/useStatus'
import { ElMessage } from 'element-plus'
import {
  Position, Goods, SwitchButton, Connection,
  Location, CircleCheck, CircleClose, SuccessFilled
} from '@element-plus/icons-vue'

const { status } = useStatus()

const showGrabDialog = ref(false)
const showPlaceDialog = ref(false)

const grabForm = ref({ target: '' })
const placeForm = ref({ target: '' })
const gripperForm = ref({ arm: 'left', action: 'open', force: 50 })
const liftForm = ref({ direction: 'up', height: 100 })

async function handleHome() {
  try {
    await robotApi.home()
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
    await robotApi.grab(grabForm.value.target)
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
    await robotApi.place(placeForm.value.target)
    ElMessage.success('放置指令已发送')
    showPlaceDialog.value = false
    placeForm.value.target = ''
  } catch (error) {
    ElMessage.error(error.response?.data?.message || '放置失败')
  }
}

async function handleGripper() {
  try {
    await robotApi.gripper(gripperForm.value.arm, gripperForm.value.action, gripperForm.value.force)
    ElMessage.success('夹爪指令已发送')
  } catch (error) {
    ElMessage.error(error.response?.data?.message || '夹爪控制失败')
  }
}

async function handleLift() {
  try {
    await robotApi.lift(liftForm.value.direction, liftForm.value.height)
    ElMessage.success('升降指令已发送')
  } catch (error) {
    ElMessage.error(error.response?.data?.message || '升降控制失败')
  }
}

async function handleCharge(action) {
  try {
    await robotApi.charge(action)
    ElMessage.success(`充电${action === 'start' ? '开始' : '停止'}指令已发送`)
  } catch (error) {
    ElMessage.error(error.response?.data?.message || '充电控制失败')
  }
}

async function handleEnable() {
  try {
    await robotApi.enable(!status.value?.enabled, false)
    ElMessage.success(`${!status.value?.enabled ? '使能' : '禁用'}成功`)
  } catch (error) {
    ElMessage.error(error.response?.data?.message || '使能操作失败')
  }
}

async function handleClearError() {
  try {
    await robotApi.enable(status.value?.enabled || true, true)
    ElMessage.success('错误已清除')
  } catch (error) {
    ElMessage.error(error.response?.data?.message || '清除错误失败')
  }
}
</script>
