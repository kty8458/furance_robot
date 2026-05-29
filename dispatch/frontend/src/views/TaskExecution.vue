<template>
  <div>
    <h2 class="page-title">任务执行</h2>

    <el-row :gutter="20">
      <el-col :span="8">
        <el-card class="exec-card">
          <template #header><span>手动触发</span></template>
          <el-select
            v-model="execRobot"
            placeholder="选择机器人"
            style="width: 100%"
            @change="onExecRobotChange"
          >
            <el-option v-for="r in robots" :key="r.id" :label="`${r.name} (${r.id})`" :value="r.id" />
          </el-select>
          <el-select
            v-model="selectedTemplate"
            placeholder="选择任务模板"
            style="width: 100%; margin-top: 8px"
            :disabled="!execRobot"
          >
            <el-option v-for="t in filteredTemplates" :key="t.id" :label="t.name" :value="t.id" />
          </el-select>
          <el-button type="primary" style="margin-top: 12px; width: 100%" @click="executeTask" :loading="executing">
            执行任务
          </el-button>
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card class="exec-card">
          <template #header><span>队列状态</span></template>
          <div class="queue-info">
            <div>
              <span class="meta-key">执行中：</span>
              <el-tag v-if="queue.current_execution_id" type="warning" size="small">#{{ queue.current_execution_id }}</el-tag>
              <span v-else class="muted">空闲</span>
            </div>
            <div style="margin-top: 8px">
              <span class="meta-key">排队中：</span>
              <span>{{ queue.queue_length }} 个</span>
            </div>
            <div v-if="queue.pending_execution_ids && queue.pending_execution_ids.length" style="margin-top: 6px">
              <el-tag
                v-for="pid in queue.pending_execution_ids"
                :key="pid"
                size="small"
                style="margin-right: 4px; margin-bottom: 4px"
              >#{{ pid }}</el-tag>
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card class="exec-card">
          <template #header><span>快捷操作</span></template>
          <el-select
            v-model="quickRobot"
            placeholder="选择机器人"
            style="width: 100%"
            @change="onQuickRobotChange"
          >
            <el-option v-for="r in robots" :key="r.id" :label="`${r.name} (${r.id})`" :value="r.id" />
          </el-select>
          <el-select
            v-model="quickWorkflow"
            placeholder="选择工作流"
            style="width: 100%; margin-top: 8px"
            :loading="quickWfLoading"
            :disabled="!quickRobot"
          >
            <el-option
              v-for="w in (workflowsByRobot[quickRobot] || [])"
              :key="w.name"
              :label="w.description ? `${w.name} - ${w.description}` : w.name"
              :value="w.name"
            />
          </el-select>
          <el-button type="warning" style="margin-top: 12px; width: 100%" @click="directCall" :loading="directing">
            直接调用子任务
          </el-button>
        </el-card>
      </el-col>
    </el-row>

    <h3 style="margin-top: 24px; color: #00d4ff;">执行历史</h3>

    <div class="filter-bar">
      <el-date-picker
        v-model="dateRange"
        type="datetimerange"
        range-separator="至"
        start-placeholder="开始时间"
        end-placeholder="结束时间"
        value-format="x"
        @change="onFilterChange"
        style="width: 380px"
      />
      <el-select v-model="orderDir" style="width: 120px; margin-left: 12px" @change="onFilterChange">
        <el-option label="时间倒序" value="desc" />
        <el-option label="时间正序" value="asc" />
      </el-select>
      <el-button style="margin-left: 12px" @click="resetFilter">重置</el-button>
    </div>

    <el-table :data="executions" class="tech-table" row-key="id" style="margin-top: 12px">
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column label="机器人" width="120">
        <template #default="{ row }">
          <el-tag v-if="row.robot_id" size="small" type="info">{{ row.robot_id }}</el-tag>
          <span v-else class="muted">-</span>
        </template>
      </el-table-column>
      <el-table-column prop="template_name" label="模板名称" min-width="140">
        <template #default="{ row }">
          {{ row.template_name || row.task_template_id }}
        </template>
      </el-table-column>
      <el-table-column label="开始时间" width="170">
        <template #default="{ row }">{{ formatTime(row.started_at) }}</template>
      </el-table-column>
      <el-table-column label="完成时间" width="170">
        <template #default="{ row }">{{ formatTime(row.completed_at) }}</template>
      </el-table-column>
      <el-table-column prop="trigger_type" label="触发" width="80" />
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="error_msg" label="错误信息" />
      <el-table-column label="操作" width="170" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="viewExecution(row.id)">详情</el-button>
          <el-button
            v-if="row.status === 'running' || row.status === 'pending'"
            size="small"
            type="danger"
            @click="cancelExecution(row.id)"
          >取消</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      style="margin-top: 12px; justify-content: flex-end;"
      background
      layout="total, sizes, prev, pager, next, jumper"
      :total="total"
      :current-page="currentPage"
      :page-size="pageSize"
      :page-sizes="[10, 20, 50, 100]"
      @update:current-page="onPageChange"
      @update:page-size="onPageSizeChange"
    />

    <el-dialog v-model="detailVisible" title="执行详情" width="92%" top="5vh">
      <template v-if="detail">
        <div class="detail-header">
          <div><span class="label">模板：</span>{{ detail.template_name || detail.task_template_id }}</div>
          <div><span class="label">触发：</span>{{ detail.trigger_type }}</div>
          <div>
            <span class="label">状态：</span>
            <el-tag :type="statusType(detail.status)" size="small">{{ statusLabel(detail.status) }}</el-tag>
          </div>
          <div><span class="label">开始：</span>{{ formatTime(detail.started_at) }}</div>
          <div><span class="label">完成：</span>{{ formatTime(detail.completed_at) }}</div>
          <div v-if="detail.error_msg" class="err"><span class="label">错误：</span>{{ detail.error_msg }}</div>
        </div>

        <div class="step-strip">
          <div
            v-for="(s, idx) in detail.steps"
            :key="s.id || `pending_${idx}`"
            class="step-card"
            :class="`step-${s.status}`"
          >
            <div class="step-card-header">
              <span class="step-no">#{{ s.step_order }}</span>
              <el-tag :type="stepTypeTagType(s.step_type)" size="small">{{ s.step_type }}</el-tag>
              <el-tag :type="statusType(s.status)" size="small">{{ s.status }}</el-tag>
            </div>
            <div class="step-label">{{ s.label || s.step_id }}</div>
            <div class="step-meta">
              <div><span class="meta-key">开始：</span>{{ formatTime(s.started_at) || '-' }}</div>
              <div><span class="meta-key">完成：</span>{{ formatTime(s.completed_at) || '-' }}</div>
              <div><span class="meta-key">用时：</span>{{ formatDuration(s.started_at, s.completed_at) }}</div>
              <div v-if="s.error_msg" class="err">错误：{{ s.error_msg }}</div>
            </div>
            <div v-if="parseSubSteps(s).length" class="sub-steps">
              <div class="sub-title">子步骤进度：</div>
              <div v-for="sub in parseSubSteps(s)" :key="sub.step_index" class="sub-row">
                <span class="sub-no">{{ sub.step_index }}.</span>
                <span class="sub-label">{{ sub.label || sub.step_id }}</span>
                <el-tag :type="statusType(sub.status)" size="small">{{ sub.status }}</el-tag>
              </div>
            </div>
          </div>
          <div v-if="!detail.steps?.length" class="empty">暂无步骤记录</div>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api/index.js'

const templates = ref([])
const robots = ref([])
const workflowsByRobot = ref({})
const executions = ref([])
const selectedTemplate = ref('')
const execRobot = ref('')
const quickRobot = ref('')
const quickWorkflow = ref('')
const quickWfLoading = ref(false)
const directing = ref(false)
const executing = ref(false)

const dateRange = ref(null)
const orderDir = ref('desc')

const currentPage = ref(1)
const pageSize = ref(20)
const total = ref(0)

const queue = ref({ current_execution_id: null, pending_execution_ids: [], queue_length: 0 })

const detailVisible = ref(false)
const detail = ref(null)

let pollTimer = null

const filteredTemplates = computed(() => {
  if (!execRobot.value) return []
  return templates.value.filter(t => t.robot_id === execRobot.value)
})

function onExecRobotChange() {
  selectedTemplate.value = ''
}

function statusType(s) {
  return { completed: 'success', running: 'warning', failed: 'danger', cancelled: 'info', pending: '' }[s] || 'info'
}

function statusLabel(s) {
  return { completed: '完成', running: '执行中', failed: '失败', cancelled: '已取消', pending: '等待中' }[s] || s
}

function stepTypeTagType(t) {
  return { workflow: 'primary', sampler: 'success', delay: 'warning' }[t] || 'info'
}

function formatTime(ts) {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  const pad = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

function formatDuration(start, end) {
  if (!start) return '-'
  const finish = end || Date.now() / 1000
  const sec = Math.max(0, Math.round(finish - start))
  if (sec < 60) return `${sec}s`
  const m = Math.floor(sec / 60); const s = sec % 60
  if (m < 60) return `${m}m${s}s`
  const h = Math.floor(m / 60); const mm = m % 60
  return `${h}h${mm}m${s}s`
}

function parseSubSteps(step) {
  const raw = step?.sub_step_results_json
  if (!raw) return []
  try { const v = JSON.parse(raw); return Array.isArray(v) ? v : [] } catch (e) { return [] }
}

async function fetchExecutions() {
  try {
    const params = {
      order: orderDir.value,
      limit: pageSize.value,
      offset: (currentPage.value - 1) * pageSize.value,
    }
    if (dateRange.value && dateRange.value.length === 2) {
      params.start_ts = Number(dateRange.value[0]) / 1000
      params.end_ts = Number(dateRange.value[1]) / 1000
    }
    const r = await api.get('/dispatch/executions', { params })
    const payload = r.data || {}
    if (Array.isArray(payload)) {
      executions.value = payload
      total.value = payload.length
    } else {
      executions.value = payload.items || []
      total.value = payload.total || 0
    }
  } catch (e) {}
  try {
    const q = await api.get('/dispatch/queue')
    queue.value = q.data || { current_execution_id: null, pending_execution_ids: [], queue_length: 0 }
  } catch (e) {}
}

async function fetchData() {
  try { const r = await api.get('/dispatch/tasks'); templates.value = r.data || [] } catch (e) {}
  try {
    const r = await api.get('/dispatch/robots')
    robots.value = r.data?.robots || []
    if (!quickRobot.value && robots.value.length) {
      quickRobot.value = robots.value[0].id
      await loadWorkflows(quickRobot.value)
    }
    if (!execRobot.value && robots.value.length) {
      execRobot.value = robots.value[0].id
    }
  } catch (e) {}
  await fetchExecutions()
}

async function loadWorkflows(robotId) {
  if (!robotId) return
  if (workflowsByRobot.value[robotId]) return
  quickWfLoading.value = true
  try {
    const r = await api.get(`/dispatch/robots/${robotId}/workflows`)
    workflowsByRobot.value[robotId] = r.data || []
  } catch (e) {
    workflowsByRobot.value[robotId] = []
    ElMessage.warning(`获取机器人 ${robotId} 工作流失败`)
  }
  quickWfLoading.value = false
}

async function onQuickRobotChange(robotId) {
  quickWorkflow.value = ''
  await loadWorkflows(robotId)
}

function onFilterChange() { currentPage.value = 1; fetchExecutions() }
function resetFilter() { dateRange.value = null; orderDir.value = 'desc'; currentPage.value = 1; fetchExecutions() }
function onPageChange(p) { currentPage.value = p; fetchExecutions() }
function onPageSizeChange(s) { pageSize.value = s; currentPage.value = 1; fetchExecutions() }

async function executeTask() {
  if (!selectedTemplate.value) { ElMessage.warning('请选择任务模板'); return }
  executing.value = true
  try {
    await api.post(`/dispatch/tasks/${selectedTemplate.value}/execute`, { trigger_type: 'manual' })
    ElMessage.success('任务已触发')
    await new Promise(r => setTimeout(r, 300))
    await fetchExecutions()
  } catch (e) { ElMessage.error(e.message || '执行失败') }
  executing.value = false
}

async function directCall() {
  if (!quickRobot.value) { ElMessage.warning('请选择机器人'); return }
  if (!quickWorkflow.value) { ElMessage.warning('请选择工作流'); return }
  directing.value = true
  try {
    await api.post(`/dispatch/robots/${quickRobot.value}/workflows/${quickWorkflow.value}/execute`)
    ElMessage.success(`已下发: ${quickRobot.value} / ${quickWorkflow.value}`)
  } catch (e) { ElMessage.error(e.message || '调用失败') }
  directing.value = false
}

async function cancelExecution(id) {
  try {
    await api.post(`/dispatch/executions/${id}/cancel`)
    ElMessage.success('已取消')
    await new Promise(r => setTimeout(r, 300))
    await fetchExecutions()
  } catch (e) { ElMessage.error(e.message || '取消失败') }
}

async function viewExecution(id) {
  try {
    const r = await api.get(`/dispatch/executions/${id}`)
    detail.value = r.data
    detailVisible.value = true
  } catch (e) { ElMessage.error(e.message || '获取详情失败') }
}

async function refreshDetailIfOpen() {
  if (detailVisible.value && detail.value?.id) {
    try {
      const r = await api.get(`/dispatch/executions/${detail.value.id}`)
      detail.value = r.data
    } catch (e) {}
  }
}

onMounted(() => {
  fetchData()
  pollTimer = setInterval(() => { fetchExecutions(); refreshDetailIfOpen() }, 2000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.page-title { color: #00d4ff; margin-bottom: 20px; }
.exec-card { background: #0a1628; border: 1px solid #1a3a5c; margin-bottom: 16px; }
.tech-table { background: #0a1628; }

.filter-bar { display: flex; align-items: center; }
.queue-info { color: var(--tech-text, #e8f0fe); font-size: 14px; }
.queue-info .muted { color: var(--tech-text-muted, #a8b8cc); }

.detail-header {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 8px 16px;
  padding: 12px 16px;
  background: #0a1628;
  border: 1px solid #1a3a5c;
  border-radius: 6px;
  color: var(--tech-text, #e8f0fe);
  margin-bottom: 16px;
}
.detail-header .label { color: var(--tech-text-muted, #a8b8cc); margin-right: 4px; }
.detail-header .err { color: #f56c6c; grid-column: 1 / -1; }

.step-strip {
  display: flex;
  gap: 12px;
  overflow-x: auto;
  padding: 8px 4px 16px;
}
.step-card {
  flex: 0 0 240px;
  background: #0a1628;
  border: 1px solid #1a3a5c;
  border-radius: 6px;
  padding: 12px;
  color: var(--tech-text, #e8f0fe);
  display: flex;
  flex-direction: column;
  gap: 8px;
  position: relative;
}
.step-card.step-running { border-color: #e6a23c; box-shadow: 0 0 8px rgba(230, 162, 60, 0.4); }
.step-card.step-completed { border-color: #67c23a; }
.step-card.step-failed { border-color: #f56c6c; box-shadow: 0 0 8px rgba(245, 108, 108, 0.4); }
.step-card.step-cancelled { border-color: #909399; }
.step-card.step-pending { border-color: #1a3a5c; opacity: 0.65; }

.step-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.step-no { color: #00d4ff; font-weight: 600; font-size: 14px; }
.step-label { font-size: 14px; font-weight: 500; word-break: break-all; }
.step-meta { font-size: 12px; color: var(--tech-text-muted, #a8b8cc); display: flex; flex-direction: column; gap: 4px; }
.meta-key { color: var(--tech-text-muted, #a8b8cc); }
.step-meta .err { color: #f56c6c; }
.sub-steps { border-top: 1px dashed #1a3a5c; padding-top: 8px; margin-top: 4px; }
.sub-title { color: var(--tech-text-muted, #a8b8cc); font-size: 12px; margin-bottom: 4px; }
.sub-row { display: flex; align-items: center; gap: 6px; font-size: 12px; margin-bottom: 4px; }
.sub-no { color: #00d4ff; min-width: 18px; }
.sub-label { flex: 1; word-break: break-all; }
.empty { color: var(--tech-text-muted, #a8b8cc); padding: 20px; }
</style>
