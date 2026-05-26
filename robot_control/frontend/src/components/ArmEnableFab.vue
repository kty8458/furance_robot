<template>
  <div class="arm-fab">
    <el-button
      v-if="status?.error_code"
      class="arm-fab-btn arm-fab-clear"
      type="warning"
      circle
      size="large"
      :loading="clearing"
      @click="handleClearError"
      title="清除错误"
    >
      <el-icon><CircleClose /></el-icon>
    </el-button>

    <el-button
      class="arm-fab-btn"
      :type="enabled ? 'danger' : 'success'"
      circle
      size="large"
      :loading="loading"
      @click="handleToggle"
      :title="enabled ? '停止机械臂' : '使能机械臂'"
    >
      <el-icon><VideoPause v-if="enabled" /><VideoPlay v-else /></el-icon>
    </el-button>

    <div class="arm-fab-label" :class="{ 'on': enabled }">
      {{ enabled ? '已使能' : '未使能' }}
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { VideoPlay, VideoPause, CircleClose } from '@element-plus/icons-vue'
import { robotApi } from '../api/robot'
import { useStatus } from '../composables/useStatus'

const { status } = useStatus()
const loading = ref(false)
const clearing = ref(false)

const enabled = computed(() => !!status.value?.enabled)

async function handleToggle() {
  const next = !enabled.value
  if (!next) {
    try {
      await ElMessageBox.confirm('确认停止机械臂使能？', '停止使能', {
        confirmButtonText: '停止',
        cancelButtonText: '取消',
        type: 'warning',
      })
    } catch {
      return
    }
  }
  loading.value = true
  try {
    await robotApi.enable(next)
    ElMessage.success(next ? '已使能' : '已停止')
  } catch (e) {
    ElMessage.error(e.message || '操作失败')
  } finally {
    loading.value = false
  }
}

async function handleClearError() {
  clearing.value = true
  try {
    await robotApi.clearError()
    ElMessage.success('错误已清除')
  } catch (e) {
    ElMessage.error(e.message || '清除失败')
  } finally {
    clearing.value = false
  }
}
</script>

<style scoped>
.arm-fab {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 2000;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  pointer-events: none;
}

.arm-fab-btn {
  pointer-events: auto;
  width: 64px !important;
  height: 64px !important;
  font-size: 26px;
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.35), 0 0 0 1px rgba(255, 255, 255, 0.08);
}

.arm-fab-clear {
  width: 48px !important;
  height: 48px !important;
  font-size: 20px;
}

.arm-fab-label {
  pointer-events: auto;
  font-size: 12px;
  padding: 2px 10px;
  border-radius: 10px;
  background: rgba(20, 30, 45, 0.85);
  color: #ff6b6b;
  border: 1px solid rgba(255, 107, 107, 0.5);
  letter-spacing: 1px;
}

.arm-fab-label.on {
  color: #00ff9d;
  border-color: rgba(0, 255, 157, 0.5);
}
</style>
