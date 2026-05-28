<template>
  <div>
    <h2 class="page-title">任务编排</h2>
    <el-button type="primary" @click="showDialog = true">新建任务模板</el-button>

    <el-table :data="templates" style="margin-top: 16px;" class="tech-table" row-key="id">
      <el-table-column prop="id" label="ID" width="150" />
      <el-table-column prop="name" label="名称" />
      <el-table-column prop="description" label="描述" />
      <el-table-column label="步骤数" width="80">
        <template #default="{ row }">
          {{ JSON.parse(row.steps_json || '[]').length }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="200">
        <template #default="{ row }">
          <el-button size="small" @click="editTemplate(row)">编辑</el-button>
          <el-button size="small" type="danger" @click="deleteTemplate(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="showDialog" :title="editingId ? '编辑任务' : '新建任务'" width="600px">
      <el-form :model="form" label-width="80px">
        <el-form-item label="ID">
          <el-input v-model="form.id" :disabled="!!editingId" />
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" />
        </el-form-item>
        <el-form-item label="步骤">
          <div v-for="(step, idx) in form.steps" :key="idx" class="step-row">
            <el-select v-model="step.type" style="width: 120px">
              <el-option label="Workflow" value="workflow" />
              <el-option label="制样机" value="sampler" />
              <el-option label="延时" value="delay" />
            </el-select>
            <el-input v-model="step.id" placeholder="步骤ID" style="width: 120px; margin-left: 8px;" />
            <el-input v-model="step.label" placeholder="标签" style="width: 150px; margin-left: 8px;" />
            <el-button type="danger" size="small" @click="form.steps.splice(idx, 1)" circle>X</el-button>
          </div>
          <el-button size="small" @click="form.steps.push({ id: '', type: 'workflow', label: '', config: {} })">+ 添加步骤</el-button>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showDialog = false">取消</el-button>
        <el-button type="primary" @click="saveTemplate">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api/index.js'

const templates = ref([])
const showDialog = ref(false)
const editingId = ref(null)
const form = ref({ id: '', name: '', description: '', steps: [] })

async function fetchTemplates() {
  try {
    const r = await api.get('/dispatch/tasks')
    templates.value = r.data || []
  } catch (e) { /* ignore */ }
}

function editTemplate(row) {
  editingId.value = row.id
  form.value = {
    id: row.id,
    name: row.name,
    description: row.description || '',
    steps: JSON.parse(row.steps_json || '[]'),
  }
  showDialog.value = true
}

async function saveTemplate() {
  try {
    if (editingId.value) {
      await api.put(`/dispatch/tasks/${editingId.value}`, form.value)
    } else {
      await api.post('/dispatch/tasks', form.value)
    }
    showDialog.value = false
    editingId.value = null
    fetchTemplates()
    ElMessage.success('保存成功')
  } catch (e) {
    ElMessage.error(e.message || '保存失败')
  }
}

async function deleteTemplate(id) {
  try {
    await ElMessageBox.confirm('确认删除该模板?', '确认', { type: 'warning' })
    await api.delete(`/dispatch/tasks/${id}`)
    fetchTemplates()
    ElMessage.success('删除成功')
  } catch (e) { /* cancelled or error */ }
}

onMounted(fetchTemplates)
</script>

<style scoped>
.page-title { color: #00d4ff; margin-bottom: 20px; }
.tech-table { background: #0a1628; }
.step-row { display: flex; align-items: center; margin-bottom: 8px; }
</style>
