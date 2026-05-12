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

          <el-form :inline="true" style="margin-bottom: 12px">
            <el-form-item label="日志级别">
              <el-select v-model="filterLevel" placeholder="全部" clearable style="width: 120px">
                <el-option label="DEBUG" value="debug" />
                <el-option label="INFO" value="info" />
                <el-option label="WARN" value="warn" />
                <el-option label="ERROR" value="error" />
              </el-select>
            </el-form-item>
            <el-form-item label="节点">
              <el-select v-model="filterNode" placeholder="全部" clearable style="width: 180px">
                <el-option v-for="n in nodeNames" :key="n" :label="n" :value="n" />
              </el-select>
            </el-form-item>
            <el-form-item label="关键词">
              <el-input v-model="filterKeyword" placeholder="搜索关键词" clearable style="width: 200px" />
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="12" style="margin-top: 12px">
      <el-col v-for="nodeName in displayedNodes" :key="nodeName" :xs="24" :sm="12" :md="8" :lg="6">
        <el-card class="tech-card node-log-card" shadow="hover">
          <template #header>
            <div class="node-log-header">
              <span :class="['status-dot', 'online']"></span>
              <span class="node-name">{{ nodeName }}</span>
              <el-tag size="small" type="info" style="margin-left: auto">
                {{ logsByNode[nodeName]?.length || 0 }}
              </el-tag>
            </div>
          </template>
          <div class="node-log-list" :ref="el => setScrollRef(nodeName, el)">
            <div
              v-for="(log, idx) in logsByNode[nodeName]"
              :key="idx"
              :class="['log-line', `log-${log.level}`]"
            >
              <span class="log-time">{{ formatTime(log.timestamp) }}</span>
              <el-tag :type="getLevelType(log.level)" size="small" class="log-level-tag">
                {{ log.level?.toUpperCase()?.slice(0, 4) }}
              </el-tag>
              <span class="log-msg">{{ log.message }}</span>
            </div>
            <div v-if="!logsByNode[nodeName]?.length" class="log-empty">暂无日志</div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, reactive } from 'vue'
import { useLogs } from '../composables/useLogs'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Document, Delete } from '@element-plus/icons-vue'

const { logs, connected, clearLogs } = useLogs()

const filterLevel = ref('')
const filterNode = ref('')
const filterKeyword = ref('')
const scrollRefs = reactive({})

function setScrollRef(name, el) {
  if (el) scrollRefs[name] = el
}

const filteredLogs = computed(() => {
  return logs.value.filter(log => {
    if (filterLevel.value && log.level !== filterLevel.value) return false
    if (filterNode.value && log.node !== filterNode.value) return false
    if (filterKeyword.value && !log.message?.includes(filterKeyword.value)) return false
    return true
  })
})

const logsByNode = computed(() => {
  const groups = {}
  for (const log of filteredLogs.value) {
    const node = log.node || 'backend'
    if (!groups[node]) groups[node] = []
    groups[node].push(log)
  }
  return groups
})

const nodeNames = computed(() => Object.keys(logsByNode.value).sort())

const displayedNodes = computed(() => {
  if (filterNode.value) return [filterNode.value]
  return nodeNames.value
})

watch(filteredLogs, async () => {
  await nextTick()
  for (const el of Object.values(scrollRefs)) {
    if (el) el.scrollTop = el.scrollHeight
  }
}, { deep: true })

function formatTime(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
}

function getLevelType(level) {
  const map = { debug: 'info', info: '', warn: 'warning', error: 'danger' }
  return map[level] || 'info'
}

async function handleClear() {
  try {
    await ElMessageBox.confirm('确定清空所有日志吗？', '确认', { type: 'warning' })
    clearLogs()
    ElMessage.success('日志已清空')
  } catch (error) {
    if (error !== 'cancel') ElMessage.error('清空失败')
  }
}
</script>

<style scoped>
.node-log-card {
  margin-bottom: 12px;
}
.node-log-header {
  display: flex;
  align-items: center;
  gap: 8px;
}
.node-name {
  font-weight: 600;
  font-size: 13px;
}
.node-log-list {
  max-height: 280px;
  overflow-y: auto;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  line-height: 1.6;
}
.log-line {
  display: flex;
  align-items: baseline;
  gap: 6px;
  padding: 2px 4px;
  border-radius: 3px;
}
.log-line:hover {
  background: rgba(0, 212, 255, 0.05);
}
.log-time {
  color: #6b7280;
  flex-shrink: 0;
  font-size: 11px;
}
.log-level-tag {
  flex-shrink: 0;
}
.log-msg {
  word-break: break-all;
  color: #e5e7eb;
}
.log-warn .log-msg { color: #ff8c00; }
.log-error .log-msg { color: #ff3b5c; }
.log-empty {
  text-align: center;
  color: #6b7280;
  padding: 20px 0;
}
</style>
