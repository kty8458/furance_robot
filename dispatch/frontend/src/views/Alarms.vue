<template>
  <div>
    <h2 class="page-title">报警页面</h2>
    <el-row :gutter="16" style="margin-bottom: 16px;">
      <el-col :span="4">
        <el-select v-model="filterLevel" placeholder="级别" clearable @change="fetchAlarms">
          <el-option label="警告" value="warning" />
          <el-option label="严重" value="critical" />
        </el-select>
      </el-col>
      <el-col :span="4">
        <el-select v-model="filterStatus" placeholder="状态" clearable @change="fetchAlarms">
          <el-option label="未确认" value="unack" />
          <el-option label="已确认" value="acked" />
        </el-select>
      </el-col>
    </el-row>

    <el-table :data="alarms" class="tech-table" row-key="id">
      <el-table-column prop="level" label="级别" width="80">
        <template #default="{ row }">
          <el-tag :type="row.level === 'critical' ? 'danger' : 'warning'" size="small">{{ row.level }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="category" label="分类" width="100" />
      <el-table-column prop="title" label="标题" width="200" />
      <el-table-column prop="message" label="消息" />
      <el-table-column prop="robot_id" label="机器人" width="120" />
      <el-table-column prop="ack_status" label="状态" width="80">
        <template #default="{ row }">
          <el-tag :type="row.ack_status === 'acked' ? 'success' : 'info'" size="small">
            {{ row.ack_status === 'acked' ? '已确认' : '未确认' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="100">
        <template #default="{ row }">
          <el-button v-if="row.ack_status === 'unack'" size="small" type="primary" @click="ackAlarm(row.id)">确认</el-button>
        </template>
      </el-table-column>
    </el-table>

    <h3 style="margin-top: 24px; color: #00d4ff;">报警规则</h3>
    <el-button size="small" type="primary" @click="showRuleDialog = true" style="margin-bottom: 12px;">添加规则</el-button>
    <el-table :data="rules" class="tech-table" row-key="id">
      <el-table-column prop="name" label="名称" />
      <el-table-column prop="category" label="分类" width="120" />
      <el-table-column prop="level" label="级别" width="80" />
      <el-table-column prop="condition_json" label="条件" />
      <el-table-column label="操作" width="80">
        <template #default="{ row }">
          <el-button size="small" type="danger" @click="deleteRule(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="showRuleDialog" title="添加报警规则" width="500px">
      <el-form :model="ruleForm" label-width="80px">
        <el-form-item label="名称"><el-input v-model="ruleForm.name" /></el-form-item>
        <el-form-item label="分类"><el-input v-model="ruleForm.category" /></el-form-item>
        <el-form-item label="级别">
          <el-select v-model="ruleForm.level"><el-option label="警告" value="warning" /><el-option label="严重" value="critical" /></el-select>
        </el-form-item>
        <el-form-item label="字段"><el-input v-model="ruleForm.field" placeholder="如: battery" /></el-form-item>
        <el-form-item label="运算符">
          <el-select v-model="ruleForm.operator">
            <el-option label="<" value="<" /><el-option label=">" value=">" /><el-option label="<=" value="<=" /><el-option label=">=" value=">=" /><el-option label="==" value="==" />
          </el-select>
        </el-form-item>
        <el-form-item label="阈值"><el-input-number v-model="ruleForm.value" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showRuleDialog = false">取消</el-button>
        <el-button type="primary" @click="createRule">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api/index.js'

const alarms = ref([])
const rules = ref([])
const filterLevel = ref('')
const filterStatus = ref('')
const showRuleDialog = ref(false)
const ruleForm = ref({ name: '', category: '', level: 'warning', field: '', operator: '<', value: 0 })

async function fetchAlarms() {
  const params = {}
  if (filterLevel.value) params.level = filterLevel.value
  if (filterStatus.value) params.ack_status = filterStatus.value
  try { const r = await api.get('/dispatch/alarms', { params }); alarms.value = r.data || [] } catch (e) {}
}

async function fetchRules() {
  try { const r = await api.get('/dispatch/alarms/rules'); rules.value = r.data || [] } catch (e) {}
}

async function ackAlarm(id) {
  try {
    await api.post(`/dispatch/alarms/${id}/ack`)
    ElMessage.success('已确认')
    fetchAlarms()
  } catch (e) { ElMessage.error(e.message) }
}

async function createRule() {
  try {
    await api.post('/dispatch/alarms/rules', {
      name: ruleForm.value.name,
      category: ruleForm.value.category,
      level: ruleForm.value.level,
      condition_json: { field: ruleForm.value.field, operator: ruleForm.value.operator, value: ruleForm.value.value },
    })
    showRuleDialog.value = false
    fetchRules()
    ElMessage.success('规则已创建')
  } catch (e) { ElMessage.error(e.message) }
}

async function deleteRule(id) {
  try {
    await api.delete(`/dispatch/alarms/rules/${id}`)
    fetchRules()
  } catch (e) {}
}

onMounted(() => { fetchAlarms(); fetchRules() })
</script>

<style scoped>
.page-title { color: #00d4ff; margin-bottom: 20px; }
.tech-table { background: #0a1628; }
</style>
