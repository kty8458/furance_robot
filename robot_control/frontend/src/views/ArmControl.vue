<template>
  <div class="arm-control">
    <el-row :gutter="20">
      <el-col :span="24">
        <el-card>
          <template #header>
            <div class="card-header">
              <el-icon><SetUp /></el-icon>
              <span style="margin-left: 8px">手臂运动控制</span>
            </div>
          </template>

          <el-form :inline="true">
            <el-form-item label="手臂">
              <el-select v-model="moveForm.arm" style="width: 120px">
                <el-option label="左臂" value="left" />
                <el-option label="右臂" value="right" />
              </el-select>
            </el-form-item>
            <el-form-item label="运动方法">
              <el-select v-model="moveForm.method" style="width: 120px">
                <el-option label="movep" value="movep" />
                <el-option label="moveL" value="moveL" />
                <el-option label="moveJ" value="moveJ" />
              </el-select>
            </el-form-item>
            <el-form-item label="坐标系">
              <el-select v-model="moveForm.coordinate" style="width: 120px">
                <el-option label="基坐标系" value="base" />
                <el-option label="工具坐标系" value="tool" />
              </el-select>
            </el-form-item>
          </el-form>

          <el-form>
            <el-row :gutter="20">
              <el-col :span="6">
                <el-form-item label="关节1">
                  <el-input-number v-model="moveForm.joint1" style="width: 100%" />
                </el-form-item>
              </el-col>
              <el-col :span="6">
                <el-form-item label="关节2">
                  <el-input-number v-model="moveForm.joint2" style="width: 100%" />
                </el-form-item>
              </el-col>
              <el-col :span="6">
                <el-form-item label="关节3">
                  <el-input-number v-model="moveForm.joint3" style="width: 100%" />
                </el-form-item>
              </el-col>
              <el-col :span="6">
                <el-form-item label="关节4">
                  <el-input-number v-model="moveForm.joint4" style="width: 100%" />
                </el-form-item>
              </el-col>
              <el-col :span="6">
                <el-form-item label="关节5">
                  <el-input-number v-model="moveForm.joint5" style="width: 100%" />
                </el-form-item>
              </el-col>
              <el-col :span="6">
                <el-form-item label="关节6">
                  <el-input-number v-model="moveForm.joint6" style="width: 100%" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item>
                  <el-button type="primary" @click="handleMove" style="width: 100%">
                    <el-icon><VideoPlay /></el-icon>
                    执行运动
                  </el-button>
                </el-form-item>
              </el-col>
            </el-row>
          </el-form>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" style="margin-top: 20px">
      <el-col :span="24">
        <el-card>
          <template #header>
            <div class="card-header">
              <el-icon><Files /></el-icon>
              <span style="margin-left: 8px">示教管理</span>
            </div>
          </template>

          <el-form :inline="true">
            <el-form-item label="手臂">
              <el-select v-model="teachForm.arm" style="width: 120px">
                <el-option label="左臂" value="left" />
                <el-option label="右臂" value="right" />
              </el-select>
            </el-form-item>
            <el-form-item label="预设位名称">
              <el-input v-model="teachForm.name" placeholder="输入预设位名称" style="width: 200px" />
            </el-form-item>
            <el-form-item>
              <el-button type="success" @click="handleTeachSave">
                <el-icon><Plus /></el-icon>
                保存当前位置
              </el-button>
            </el-form-item>
            <el-form-item>
              <el-button @click="refreshTeachList">
                <el-icon><Refresh /></el-icon>
                刷新列表
              </el-button>
            </el-form-item>
          </el-form>

          <el-table :data="teachList" border style="width: 100%">
            <el-table-column prop="name" label="预设位名称" />
            <el-table-column prop="arm" label="手臂" :formatter="formatArm" />
            <el-table-column label="操作" width="250">
              <template #default="{ row }">
                <el-button type="primary" size="small" @click="handleTeachExec(row)">
                  <el-icon><VideoPlay /></el-icon>
                  执行
                </el-button>
                <el-button type="danger" size="small" @click="handleTeachDelete(row)">
                  <el-icon><Delete /></el-icon>
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { armApi } from '../api/arm'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  SetUp, Files, Plus, Refresh, VideoPlay, Delete
} from '@element-plus/icons-vue'

const moveForm = ref({
  arm: 'left',
  method: 'moveJ',
  coordinate: 'base',
  joint1: 0,
  joint2: 0,
  joint3: 0,
  joint4: 0,
  joint5: 0,
  joint6: 0
})

const teachForm = ref({ arm: 'left', name: '' })
const teachList = ref([])

onMounted(refreshTeachList)

async function refreshTeachList() {
  try {
    const response = await armApi.teachList()
    teachList.value = response.data || []
  } catch (error) {
    ElMessage.error(error.response?.data?.message || '获取示教列表失败')
  }
}

async function handleMove() {
  try {
    await armApi.move({
      arm: moveForm.value.arm,
      method: moveForm.value.method,
      coordinate: moveForm.value.coordinate,
      joint_angles: {
        joint1: moveForm.value.joint1,
        joint2: moveForm.value.joint2,
        joint3: moveForm.value.joint3,
        joint4: moveForm.value.joint4,
        joint5: moveForm.value.joint5,
        joint6: moveForm.value.joint6
      }
    })
    ElMessage.success('运动指令已发送')
  } catch (error) {
    ElMessage.error(error.response?.data?.message || '运动失败')
  }
}

async function handleTeachSave() {
  if (!teachForm.value.name) {
    ElMessage.warning('请输入预设位名称')
    return
  }
  try {
    await armApi.teachSave(teachForm.value.arm, teachForm.value.name)
    ElMessage.success('保存成功')
    teachForm.value.name = ''
    refreshTeachList()
  } catch (error) {
    ElMessage.error(error.response?.data?.message || '保存失败')
  }
}

async function handleTeachExec(row) {
  try {
    await armApi.teachExec(row.arm, row.name)
    ElMessage.success('执行指令已发送')
  } catch (error) {
    ElMessage.error(error.response?.data?.message || '执行失败')
  }
}

async function handleTeachDelete(row) {
  try {
    await ElMessageBox.confirm(`确定删除预设位 "${row.name}" 吗？`, '确认', { type: 'warning' })
    await armApi.teachDelete(row.name)
    ElMessage.success('删除成功')
    refreshTeachList()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(error.response?.data?.message || '删除失败')
    }
  }
}

function formatArm(row) {
  return row.arm === 'left' ? '左臂' : '右臂'
}
</script>

<style scoped>
.arm-control {
  padding: 20px;
}

.card-header {
  display: flex;
  align-items: center;
}
</style>
