<template>
  <div class="tech-page">
    <el-row :gutter="20">
      <!-- 1) ROS2 Node Management -->
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
                <el-tag :type="row.type === 'launch' ? 'warning' : ''" size="small">{{ row.type === 'launch' ? 'Launch' : 'Node' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="status" label="状态" width="120">
              <template #default="{ row }">
                <el-tag :type="row.status === 'running' ? 'success' : 'info'">{{ row.status === 'running' ? '运行中' : '停止' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="280">
              <template #default="{ row }">
                <el-button v-if="row.status !== 'running' && row.name !== 'node_manager'" type="success" size="small" @click="handleStart(row.name)">
                  <el-icon><VideoPlay /></el-icon>启动
                </el-button>
                <el-button v-if="row.status === 'running' && row.name !== 'node_manager'" type="danger" size="small" @click="handleStop(row.name)">
                  <el-icon><SwitchButton /></el-icon>停止
                </el-button>
                <el-button v-if="row.name !== 'node_manager'" size="small" @click="openLogDrawer(row.name)">
                  <el-icon><Document /></el-icon>日志
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" style="margin-top: 16px">
      <!-- 2) Backend logs -->
      <el-col :span="12">
        <el-card class="tech-card">
          <template #header>
            <div class="tech-card-header">
              <el-icon><Document /></el-icon>
              <span style="margin-left: 8px">后台日志</span>
              <el-button size="small" @click="fetchBackendLog" :loading="backendLogLoading" style="margin-left: auto">
                <el-icon><Refresh /></el-icon>
                查看最新200条
              </el-button>
            </div>
          </template>
          <div class="log-container" style="height: 340px">
            <div v-for="(line, idx) in backendLines" :key="idx" class="log-line">{{ line }}</div>
            <div v-if="!backendLines.length && !backendLogLoading" class="log-empty" style="padding: 20px 0">点击「查看最新200条」加载日志</div>
            <div v-if="backendLogLoading" class="log-loading"><el-icon class="is-loading"><Loading /></el-icon>加载中...</div>
          </div>
        </el-card>
      </el-col>

      <!-- 3) Log management -->
      <el-col :span="12">
        <el-card class="tech-card">
          <template #header>
            <div class="tech-card-header">
              <el-icon><FolderOpened /></el-icon>
              <span style="margin-left: 8px">日志管理</span>
            </div>
          </template>
          <el-row :gutter="12" style="margin-bottom: 12px">
            <el-col :span="6">
              <div style="font-size: 12px; color: #9ca3af; margin-bottom: 4px">来源</div>
              <el-select v-model="logMgr.source" style="width: 100%" @change="onSourceChange">
                <el-option label="后台日志" value="backend" />
                <el-option label="ROS2节点" value="ros2" />
              </el-select>
            </el-col>
            <el-col :span="6">
              <div style="font-size: 12px; color: #9ca3af; margin-bottom: 4px">日期</div>
              <el-select v-model="logMgr.date" style="width: 100%" placeholder="选择日期" @change="onDateChange">
                <el-option v-for="d in logMgr.dates" :key="d" :label="d" :value="d" />
              </el-select>
            </el-col>
            <el-col :span="6" v-if="logMgr.source === 'ros2'">
              <div style="font-size: 12px; color: #9ca3af; margin-bottom: 4px">节点</div>
              <el-select v-model="logMgr.node" style="width: 100%" placeholder="选择节点" :disabled="!logMgr.nodes.length">
                <el-option v-for="n in logMgr.nodes" :key="n" :label="n" :value="n" />
              </el-select>
            </el-col>
            <el-col :span="6">
              <div style="font-size: 12px; color: #9ca3af; margin-bottom: 4px">&nbsp;</div>
              <el-button size="small" :disabled="!canDownload" @click="downloadLog">下载日志</el-button>
            </el-col>
          </el-row>
          <div class="log-container" style="height: 280px">
            <div v-for="(line, idx) in logMgr.lines" :key="idx" class="log-line">{{ line }}</div>
            <div v-if="!logMgr.lines.length" class="log-empty" style="padding: 14px 0">选择来源和日期查看历史日志</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- ROS2 Node Log Drawer (unchanged) -->
    <el-drawer v-model="logDrawerVisible" :title="`日志 - ${logNodeName}`" direction="rtl" size="70%" :destroy-on-close="true" @close="closeLogDrawer">
      <div class="log-toolbar">
        <el-button size="small" @click="fetchLogs"><el-icon><Refresh /></el-icon>刷新</el-button>
        <el-button size="small" @click="scrollLogToBottom"><el-icon><Bottom /></el-icon>底部</el-button>
        <el-switch v-model="logAutoRefresh" active-text="自动刷新" inactive-text="" style="margin-left: 12px" />
        <el-select v-model="logTail" size="small" style="width: 120px; margin-left: 12px" @change="resetAndFetch">
          <el-option :value="100" label="最近100行" />
          <el-option :value="200" label="最近200行" />
          <el-option :value="500" label="最近500行" />
        </el-select>
        <span style="margin-left: auto; color: #999; font-size: 12px">共 {{ logTotal }} 行</span>
      </div>
      <div class="log-container" ref="logContainerRef">
        <div v-for="(line, idx) in logLines" :key="idx" :class="['log-line', getLogClass(line)]">{{ line }}</div>
        <div v-if="logLoading" class="log-loading"><el-icon class="is-loading"><Loading /></el-icon>加载中...</div>
        <div v-if="!logLines.length && !logLoading" class="log-empty">暂无日志，等待节点输出...</div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, reactive, computed, nextTick, onMounted, onUnmounted, watch } from 'vue'
import { ros2Api } from '../api/ros2'
import { systemLogsApi } from '../api/systemLogs'
import { ElMessage } from 'element-plus'
import { Cpu, Refresh, VideoPlay, SwitchButton, Document, Bottom, Loading, FolderOpened } from '@element-plus/icons-vue'

// ----- ROS2 nodes -----
const nodes = ref([])
onMounted(refreshNodes)

async function refreshNodes() {
  try {
    const r = await ros2Api.listNodes()
    nodes.value = r.data?.data || r.data || []
  } catch (e) { ElMessage.error(e.message || '获取节点列表失败') }
}

async function handleStart(name) {
  try {
    await ros2Api.startNode(name)
    ElMessage.success(`节点 ${name} 启动指令已发送`)
    refreshNodes()
  } catch (e) { ElMessage.error(e.message || '启动节点失败') }
}

async function handleStop(name) {
  try {
    await ros2Api.stopNode(name)
    ElMessage.success(`节点 ${name} 停止指令已发送`)
    refreshNodes()
  } catch (e) { ElMessage.error(e.message || '停止节点失败') }
}

// ----- ROS2 node log drawer -----
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
  if (val) { autoRefreshTimer = setInterval(fetchLogs, 2000) }
  else { clearInterval(autoRefreshTimer); autoRefreshTimer = null }
})
onUnmounted(() => { if (autoRefreshTimer) clearInterval(autoRefreshTimer) })

async function openLogDrawer(name) {
  logNodeName.value = name; logLines.value = []; logTotal.value = 0
  logDrawerVisible.value = true
  await fetchLogs()
  if (logAutoRefresh.value && !autoRefreshTimer) autoRefreshTimer = setInterval(fetchLogs, 2000)
}
function closeLogDrawer() {
  if (autoRefreshTimer) { clearInterval(autoRefreshTimer); autoRefreshTimer = null }
  logLines.value = []
}
function resetAndFetch() { logLines.value = []; logTotal.value = 0; fetchLogs() }
async function fetchLogs() {
  logLoading.value = true
  try {
    const r = await ros2Api.nodeLogs(logNodeName.value, logTail.value)
    const data = (r.data?.data || r.data)
    logLines.value = data?.logs || []
    logTotal.value = data?.total || logLines.value.length
    await nextTick()
    if (logAutoRefresh.value) scrollLogToBottom()
  } catch { /* ignore */ } finally { logLoading.value = false }
}
function scrollLogToBottom() {
  const el = logContainerRef.value
  if (el) el.scrollTop = el.scrollHeight
}
function getLogClass(line) {
  if (typeof line !== 'string') return ''
  const l = line.toLowerCase()
  if (l.includes('[error]') || l.includes('[fatal]')) return 'log-error'
  if (l.includes('[warn]')) return 'log-warn'
  return ''
}

// ----- Backend log -----
const backendLines = ref([])
const backendLogLoading = ref(false)
async function fetchBackendLog() {
  backendLogLoading.value = true
  try {
    const r = await systemLogsApi.listBackendDates()
    const dates = (r.data?.data || r.data)?.dates || []
    if (!dates.length) {
      backendLines.value = ['暂无日志文件']
      return
    }
    const today = dates[0]
    const r2 = await systemLogsApi.viewBackend(today, 200)
    const data = r2.data?.data || r2.data
    backendLines.value = data?.lines || []
  } catch { /* ignore */ } finally { backendLogLoading.value = false }
}

// ----- Log management -----
const logMgr = reactive({
  source: 'backend',
  dates: [],
  date: '',
  nodes: [],   // available nodes for selected ros2 date
  node: '',
  lines: [],
})
const ros2DateNodeMap = ref({})  // date -> [node names]

const canDownload = computed(() => {
  if (!logMgr.date) return false
  if (logMgr.source === 'ros2') return !!logMgr.node
  return true
})

onMounted(loadDates)

function onSourceChange() {
  logMgr.dates = []
  logMgr.date = ''
  logMgr.nodes = []
  logMgr.node = ''
  logMgr.lines = []
  loadDates()
}

function onDateChange() {
  if (logMgr.source === 'ros2') {
    logMgr.nodes = ros2DateNodeMap.value[logMgr.date] || []
    logMgr.node = ''
  }
  viewLog()
}

async function loadDates() {
  try {
    if (logMgr.source === 'backend') {
      const r = await systemLogsApi.listBackendDates()
      logMgr.dates = (r.data?.data || r.data)?.dates || []
    } else {
      const r = await systemLogsApi.listRos2Dates()
      const arr = (r.data?.data || r.data)?.dates || []
      logMgr.dates = arr.map(d => d.date)
      const map = {}
      for (const d of arr) map[d.date] = d.nodes || []
      ros2DateNodeMap.value = map
    }
  } catch { logMgr.dates = [] }
}

async function viewLog() {
  if (!logMgr.date) return
  try {
    if (logMgr.source === 'backend') {
      const r = await systemLogsApi.viewBackend(logMgr.date)
      const data = r.data?.data || r.data
      logMgr.lines = data?.lines || []
    } else {
      const r = await systemLogsApi.viewRos2(logMgr.date)
      const data = r.data?.data || r.data
      const segs = data?.segments || []
      logMgr.lines = []
      for (const seg of segs) {
        logMgr.lines.push(`--- ${seg.node} (${seg.session}) ---`)
        logMgr.lines.push(...seg.lines)
      }
    }
  } catch { logMgr.lines = ['加载失败'] }
}

function downloadLog() {
  if (!logMgr.date) return
  if (logMgr.source === 'backend') {
    window.open(systemLogsApi.downloadBackend(logMgr.date))
  } else if (logMgr.node) {
    window.open(systemLogsApi.downloadRos2Node(logMgr.node, logMgr.date))
  }
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
.log-line:hover { background: rgba(0, 212, 255, 0.05); }
.log-warn { color: #ff8c00; }
.log-error { color: #ff3b5c; }
.log-loading { position: absolute; top: 12px; right: 16px; color: #999; font-size: 12px; display: flex; align-items: center; gap: 4px; }
.log-empty { text-align: center; color: #6b7280; padding: 40px 0; }
</style>