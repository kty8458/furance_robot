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
            <el-table-column prop="name" label="节点名称" />
            <el-table-column prop="status" label="状态" width="150">
              <template #default="{ row }">
                <el-tag :type="row.status === 'running' ? 'success' : 'info'">
                  {{ row.status === 'running' ? '运行中' : '停止' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="200">
              <template #default="{ row }">
                <el-button
                  v-if="row.status !== 'running'"
                  type="success"
                  size="small"
                  @click="handleStart(row.name)"
                >
                  <el-icon><VideoPlay /></el-icon>
                  启动
                </el-button>
                <el-button
                  v-else
                  type="danger"
                  size="small"
                  @click="handleStop(row.name)"
                >
                  <el-icon><SwitchButton /></el-icon>
                  停止
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
import { ros2Api } from '../api/ros2'
import { ElMessage } from 'element-plus'
import { Cpu, Refresh, VideoPlay, SwitchButton } from '@element-plus/icons-vue'

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
</script>
