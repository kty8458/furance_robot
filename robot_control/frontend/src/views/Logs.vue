<template>
  <div class="tech-page">
    <el-row :gutter="20">
      <el-col :span="24">
        <el-card class="tech-card">
          <template #header>
            <div class="tech-card-header">
              <el-icon><Document /></el-icon>
              <span style="margin-left: 8px">运行日志</span>
              <span style="margin-left: 10px">
                <span :class="['status-dot', connected ? 'online' : 'offline']"></span>
                <el-tag :type="connected ? 'success' : 'danger'" size="small">
                  {{ connected ? '已连接' : '连接断开' }}
                </el-tag>
              </span>
              <el-button @click="handleClear" style="margin-left: auto" type="danger">
                <el-icon><Delete /></el-icon>
                清空日志
              </el-button>
            </div>
          </template>

          <el-form :inline="true" style="margin-bottom: 20px">
            <el-form-item label="日志级别">
              <el-select v-model="filterLevel" placeholder="全部" clearable style="width: 150px">
                <el-option label="DEBUG" value="debug" />
                <el-option label="INFO" value="info" />
                <el-option label="WARNING" value="warning" />
                <el-option label="ERROR" value="error" />
              </el-select>
            </el-form-item>
            <el-form-item label="来源">
              <el-input v-model="filterSource" placeholder="过滤来源" clearable style="width: 200px" />
            </el-form-item>
            <el-form-item label="关键词">
              <el-input v-model="filterKeyword" placeholder="搜索关键词" clearable style="width: 250px" />
            </el-form-item>
          </el-form>

          <el-table
            :data="filteredLogs"
            border
            style="width: 100%"
            height="calc(100vh - 280px)"
            ref="tableRef"
          >
            <el-table-column prop="timestamp" label="时间" width="180">
              <template #default="{ row }">
                {{ formatTimestamp(row.timestamp) }}
              </template>
            </el-table-column>
            <el-table-column prop="level" label="级别" width="100">
              <template #default="{ row }">
                <el-tag :type="getLevelType(row.level)" size="small">
                  {{ row.level?.toUpperCase() }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="source" label="来源" width="150" />
            <el-table-column prop="message" label="消息" show-overflow-tooltip />
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { useLogs } from '../composables/useLogs'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Document, Delete } from '@element-plus/icons-vue'

const { logs, connected, clearLogs } = useLogs()
const tableRef = ref(null)

const filterLevel = ref('')
const filterSource = ref('')
const filterKeyword = ref('')

const filteredLogs = computed(() => {
  return logs.value.filter(log => {
    if (filterLevel.value && log.level !== filterLevel.value) return false
    if (filterSource.value && !log.source?.includes(filterSource.value)) return false
    if (filterKeyword.value && !log.message?.includes(filterKeyword.value)) return false
    return true
  })
})

watch(logs, async () => {
  await nextTick()
  if (tableRef.value) {
    const table = tableRef.value
    const bodyWrapper = table.$el.querySelector('.el-scrollbar__wrap')
    if (bodyWrapper) {
      bodyWrapper.scrollTop = bodyWrapper.scrollHeight
    }
  }
}, { deep: true })

function formatTimestamp(ts) {
  if (!ts) return '--'
  const date = new Date(ts)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false
  })
}

function getLevelType(level) {
  const map = {
    debug: 'info',
    info: 'info',
    warning: 'warning',
    error: 'danger'
  }
  return map[level] || 'info'
}

async function handleClear() {
  try {
    await ElMessageBox.confirm('确定清空所有日志吗？', '确认', { type: 'warning' })
    clearLogs()
    ElMessage.success('日志已清空')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('清空失败')
    }
  }
}
</script>
