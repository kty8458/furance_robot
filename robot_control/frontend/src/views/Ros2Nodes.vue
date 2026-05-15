<template>
  <div class="tech-page">
    <el-row :gutter="20">
      <el-col :span="24">
        <el-card class="tech-card">
          <template #header>
            <div class="tech-card-header">
              <el-icon><Cpu /></el-icon>
              <span style="margin-left: 8px">ROS2节点管理</span>
              <el-button @click="refreshNodes" style="margin-left: auto">
                <el-icon><Refresh /></el-icon>
                刷新列表
              </el-button>
            </div>
          </template>

          <el-table :data="nodes" border style="width: 100%">
            <el-table-column prop="name" label="名称" />
            <el-table-column prop="type" label="类型" width="100">
              <template #default="{ row }">
                <el-tag :type="row.type === 'launch' ? 'warning' : ''" size="small">
                  {{ row.type === 'launch' ? 'Launch' : 'Node' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="status" label="状态" width="120">
              <template #default="{ row }">
                <el-tag :type="row.status === 'running' ? 'success' : 'info'">
                  {{ row.status === 'running' ? '运行中' : '停止' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="280">
              <template #default="{ row }">
                <el-button
                  v-if="row.status !== 'running' && row.name !== 'node_manager'"
                  type="success"
                  size="small"
                  @click="handleStart(row.name)"
                >
                  <el-icon><VideoPlay /></el-icon>
                  启动
                </el-button>
                <el-button
                  v-if="row.status === 'running' && row.name !== 'node_manager'"
                  type="danger"
                  size="small"
                  @click="handleStop(row.name)"
                >
                  <el-icon><SwitchButton /></el-icon>
                  停止
                </el-button>
                <el-button
                  v-if="row.name !== 'node_manager'"
                  size="small"
                  @click="openLogDrawer(row.name)"
                >
                  <el-icon><Document /></el-icon>
                  日志
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <!-- Log Drawer -->
    <el-drawer
      v-model="logDrawerVisible"
      :title="`日志 - ${logNodeName}`"
      direction="rtl"
      size="70%"
      :destroy-on-close="true"
      @close="closeLogDrawer"
    >
      <div class="log-toolbar">
        <el-button size="small" @click="fetchLogs">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
        <el-button size="small" @click="scrollLogToBottom">
          <el-icon><Bottom /></el-icon>
          底部
        </el-button>
        <el-switch
          v-model="logAutoRefresh"
          active-text="自动刷新"
          inactive-text=""
          style="margin-left: 12px"
        />
        <el-select v-model="logTail" size="small" style="width: 120px; margin-left: 12px" @change="resetAndFetch">
          <el-option :value="100" label="最近100行" />
          <el-option :value="200" label="最近200行" />
          <el-option :value="500" label="最近500行" />
        </el-select>
        <span style="margin-left: auto; color: #999; font-size: 12px">
          共 {{ logTotal }} 行
        </span>
      </div>
      <div class="log-container" ref="logContainerRef">
        <div
          v-for="(line, idx) in logLines"
          :key="idx"
          :class="['log-line', getLogClass(line)]"
        >{{ line }}</div>
        <div v-if="logLoading" class="log-loading">
          <el-icon class="is-loading"><Loading /></el-icon>
          加载中...
        </div>
        <div v-if="!logLines.length && !logLoading" class="log-empty">暂无日志，等待节点输出...</div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted, onUnmounted, watch } from 'vue'
import { ros2Api } from '../api/ros2'
import { ElMessage } from 'element-plus'
import { Cpu, Refresh, VideoPlay, SwitchButton, Document, Bottom, Loading } from '@element-plus/icons-vue'

const nodes = ref([])

onMounted(refreshNodes)

async function refreshNodes() {
  try {
    const response = await ros2Api.listNodes()
    const payload = response.data
    nodes.value = payload?.data || payload || []
  } catch (error) {
    ElMessage.error(error.message || '获取节点列表失败')
  }
}

async function handleStart(name) {
  try {
    await ros2Api.startNode(name)
    ElMessage.success(`节点 ${name} 启动指令已发送`)
    refreshNodes()
  } catch (error) {
    ElMessage.error(error.message || '启动节点失败')
  }
}

async function handleStop(name) {
  try {
    await ros2Api.stopNode(name)
    ElMessage.success(`节点 ${name} 停止指令已发送`)
    refreshNodes()
  } catch (error) {
    ElMessage.error(error.message || '停止节点失败')
  }
}

// --- Log drawer ---
const logDrawerVisible = ref(false)
const logNodeName = ref('')
const logLines = ref([])
const logLoading = ref(false)
const logTotal = ref(0)
const logAutoRefresh = ref(true)
const logTail = ref(200)
const logContainerRef = ref(null)
let autoRefreshTimer = null

watch(logAutoRefresh, (val) => {
  if (val) {
    autoRefreshTimer = setInterval(fetchLogs, 2000)
  } else {
    clearInterval(autoRefreshTimer)
    autoRefreshTimer = null
  }
})

onUnmounted(() => {
  if (autoRefreshTimer) clearInterval(autoRefreshTimer)
})

async function openLogDrawer(name) {
  logNodeName.value = name
  logLines.value = []
  logTotal.value = 0
  logDrawerVisible.value = true
  await fetchLogs()
  if (logAutoRefresh.value && !autoRefreshTimer) {
    autoRefreshTimer = setInterval(fetchLogs, 2000)
  }
}

function closeLogDrawer() {
  if (autoRefreshTimer) {
    clearInterval(autoRefreshTimer)
    autoRefreshTimer = null
  }
  logLines.value = []
}

function resetAndFetch() {
  logLines.value = []
  logTotal.value = 0
  fetchLogs()
}

async function fetchLogs() {
  logLoading.value = true
  try {
    const response = await ros2Api.nodeLogs(logNodeName.value, logTail.value)
    const payload = response.data
    const data = payload?.data || payload
    const lines = data?.logs || []
    logLines.value = lines
    logTotal.value = data?.total || lines.length
    await nextTick()
    if (logAutoRefresh.value) scrollLogToBottom()
  } catch (error) {
    // silently ignore
  } finally {
    logLoading.value = false
  }
}

function scrollLogToBottom() {
  const el = logContainerRef.value
  if (el) el.scrollTop = el.scrollHeight
}

function getLogClass(line) {
  if (typeof line !== 'string') return ''
  const lower = line.toLowerCase()
  if (lower.includes('[error]') || lower.includes('[fatal]')) return 'log-error'
  if (lower.includes('[warn]')) return 'log-warn'
  return ''
}
</script>

<style scoped>
.log-toolbar {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
}
.log-container {
  background: #1e1e1e;
  border-radius: 4px;
  height: calc(100vh - 160px);
  overflow-y: auto;
  padding: 12px;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.6;
  position: relative;
}
.log-line {
  color: #d4d4d4;
  white-space: pre-wrap;
  word-break: break-all;
  padding: 1px 0;
}
.log-line:hover {
  background: rgba(0, 212, 255, 0.05);
}
.log-warn {
  color: #ff8c00;
}
.log-error {
  color: #ff3b5c;
}
.log-loading {
  position: absolute;
  top: 12px;
  right: 16px;
  color: #999;
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 4px;
}
.log-empty {
  text-align: center;
  color: #6b7280;
  padding: 40px 0;
}
</style>
