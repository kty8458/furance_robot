<template>
  <div class="tech-page">
    <el-row :gutter="20">
      <el-col :span="12">
        <el-card class="tech-card">
          <template #header>
            <div class="tech-card-header">
              <el-icon><Monitor /></el-icon>
              <span style="margin-left: 8px">制样机状态</span>
              <el-tag :type="getStatusType(samplerStatus?.status)" size="small" style="margin-left: 10px">{{ samplerStatus?.status || '未知' }}</el-tag>
            </div>
          </template>

          <el-descriptions :column="1" border>
            <el-descriptions-item label="状态">
              <el-tag :type="getStatusType(samplerStatus?.status)" size="large">
                {{ samplerStatus?.status || '未知' }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="进度">
              <el-progress :percentage="samplerStatus?.progress || 0" :stroke-width="12" />
            </el-descriptions-item>
            <el-descriptions-item label="当前步骤">
              {{ samplerStatus?.current_step || '--' }}
            </el-descriptions-item>
            <el-descriptions-item label="错误信息">
              <span v-if="samplerStatus?.error" style="color: #ff3b5c">{{ samplerStatus.error }}</span>
              <span v-else>--</span>
            </el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card class="tech-card">
          <template #header>
            <div class="tech-card-header">
              <el-icon><Setting /></el-icon>
              <span style="margin-left: 8px">制样机控制</span>
            </div>
          </template>

          <el-button type="success" @click="handleStart" style="width: 100%; margin-bottom: 15px; height: 50px; font-size: 16px">
            <el-icon><VideoPlay /></el-icon>
            开始制样
          </el-button>

          <el-button type="danger" @click="handleStop" style="width: 100%; margin-bottom: 15px; height: 50px; font-size: 16px">
            <el-icon><VideoPause /></el-icon>
            停止制样
          </el-button>

          <el-button type="primary" @click="loadSamplerStatus" style="width: 100%; height: 50px; font-size: 16px">
            <el-icon><Refresh /></el-icon>
            查询状态
          </el-button>
        </el-card>

        <el-card class="tech-card" style="margin-top: 20px">
          <template #header>
            <div class="tech-card-header">
              <el-icon><Document /></el-icon>
              <span style="margin-left: 8px">制样参数</span>
            </div>
          </template>

          <el-form :inline="true">
            <el-form-item label="样品数量">
              <el-input-number v-model="samplerParams.count" :min="1" :max="100" />
            </el-form-item>
            <el-form-item label="制样模式">
              <el-select v-model="samplerParams.mode" style="width: 150px">
                <el-option label="标准模式" value="standard" />
                <el-option label="快速模式" value="fast" />
                <el-option label="精细模式" value="fine" />
              </el-select>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Monitor, Setting, VideoPlay, VideoPause, Refresh, Document } from '@element-plus/icons-vue'
import { samplerApi } from '../api/sampler'

const samplerStatus = ref(null)
const samplerParams = ref({ count: 1, mode: 'standard' })
let refreshTimer = null

async function loadSamplerStatus() {
  try {
    const response = await samplerApi.getStatus()
    samplerStatus.value = response.data
  } catch (error) {
    // 静默失败
  }
}

async function handleStart() {
  try {
    await ElMessageBox.confirm(`确定要开始制样吗?\n样品数量: ${samplerParams.value.count}\n制样模式: ${samplerParams.value.mode}`, '确认', {
      type: 'info'
    })
    await samplerApi.sendCommand('start', samplerParams.value)
    ElMessage.success('制样已开始')
    loadSamplerStatus()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(error.response?.data?.message || '开始制样失败')
    }
  }
}

async function handleStop() {
  try {
    await ElMessageBox.confirm('确定要停止制样吗?', '确认', {
      type: 'warning'
    })
    await samplerApi.sendCommand('stop', {})
    ElMessage.success('制样已停止')
    loadSamplerStatus()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(error.response?.data?.message || '停止制样失败')
    }
  }
}

function getStatusType(status) {
  switch (status) {
    case 'running': return 'success'
    case 'idle': return 'info'
    case 'error': return 'danger'
    case 'completed': return 'success'
    case 'stopped': return 'warning'
    default: return 'info'
  }
}

onMounted(() => {
  loadSamplerStatus()
  refreshTimer = setInterval(loadSamplerStatus, 5000)
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})
</script>
