<template>
  <div class="tech-page">
    <el-row :gutter="20">
      <el-col :span="24">
        <el-card class="tech-card">
          <template #header>
            <div class="tech-card-header">
              <el-icon><Monitor /></el-icon>
              <span style="margin-left: 8px">机器人状态监控</span>
              <span style="margin-left: 10px">
                <span :class="['status-dot', connected ? 'online' : 'offline']"></span>
                <el-tag :type="connected ? 'success' : 'danger'" size="small">{{ connected ? '在线' : '离线' }}</el-tag>
              </span>
            </div>
          </template>

          <el-descriptions :column="2" border>
            <el-descriptions-item label="位置信息">
              <div v-if="status?.position">
                X: {{ status.position.x?.toFixed(2) ?? '--' }}, Y: {{ status.position.y?.toFixed(2) ?? '--' }}, θ: {{ status.position.theta?.toFixed(2) ?? '--' }}°
              </div>
              <span v-else>--</span>
            </el-descriptions-item>
            <el-descriptions-item label="当前地图">
              {{ status?.current_map || '--' }}
            </el-descriptions-item>
            <el-descriptions-item label="电量">
              <el-progress :percentage="status?.battery || 0" :status="status?.battery < 20 ? 'exception' : 'normal'" :stroke-width="8" style="width: 120px" />
              <span style="margin-left: 10px">{{ status?.battery || 0 }}%</span>
            </el-descriptions-item>
            <el-descriptions-item label="充电状态">
              <el-tag :type="status?.charging ? 'success' : 'info'">{{ status?.charging ? '正在充电' : '未充电' }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="使能状态">
              <el-tag :type="status?.enabled ? 'success' : 'danger'">{{ status?.enabled ? '已使能' : '未使能' }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="升降高度">
              {{ status?.lift_height?.toFixed(1) ?? 0 }}mm
            </el-descriptions-item>
            <el-descriptions-item label="左夹爪状态">
              <div>
                <el-tag :type="status?.gripper?.left?.state === 'closed' ? 'success' : 'info'">
                  {{ status?.gripper?.left?.state === 'closed' ? '闭合' : '打开' }}
                </el-tag>
                <span style="margin-left: 10px">力: {{ status?.gripper?.left?.force?.toFixed(1) ?? 0 }}N</span>
              </div>
            </el-descriptions-item>
            <el-descriptions-item label="右夹爪状态">
              <div>
                <el-tag :type="status?.gripper?.right?.state === 'closed' ? 'success' : 'info'">
                  {{ status?.gripper?.right?.state === 'closed' ? '闭合' : '打开' }}
                </el-tag>
                <span style="margin-left: 10px">力: {{ status?.gripper?.right?.force?.toFixed(1) ?? 0 }}N</span>
              </div>
            </el-descriptions-item>
            <el-descriptions-item label="左手臂状态">
              <div>
                <el-tag :type="status?.arm?.left?.status === 'idle' ? 'success' : 'warning'">
                  {{ status?.arm?.left?.status || '未知' }}
                </el-tag>
                <div style="margin-top: 4px">关节: {{ formatJointAngles(status?.arm?.left?.joint_angles) }}</div>
                <div style="margin-top: 2px; color: #00d4ff">
                  末端: {{ formatEE(status?.arm?.left?.end_effector) }}
                  <span v-if="status?.arm?.left?.coordinate_frame" style="color: #6b7280"> [{{ status.arm.left.coordinate_frame }}]</span>
                </div>
              </div>
            </el-descriptions-item>
            <el-descriptions-item label="右手臂状态">
              <div>
                <el-tag :type="status?.arm?.right?.status === 'idle' ? 'success' : 'warning'">
                  {{ status?.arm?.right?.status || '未知' }}
                </el-tag>
                <div style="margin-top: 4px">关节: {{ formatJointAngles(status?.arm?.right?.joint_angles) }}</div>
                <div style="margin-top: 2px; color: #00d4ff">
                  末端: {{ formatEE(status?.arm?.right?.end_effector) }}
                  <span v-if="status?.arm?.right?.coordinate_frame" style="color: #6b7280"> [{{ status.arm.right.coordinate_frame }}]</span>
                </div>
              </div>
            </el-descriptions-item>
            <el-descriptions-item label="任务状态">
              <el-tag :type="status?.task_status === 'idle' ? 'info' : 'warning'">
                {{ taskStatusText }}
              </el-tag>
            </el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useStatus } from '../composables/useStatus'
import { Monitor } from '@element-plus/icons-vue'

const { status, connected } = useStatus()

const taskStatusMap = { idle: '空闲', moving: '移动中', working: '作业中' }
const taskStatusText = computed(() => taskStatusMap[status.value?.task_status] || '未知')

function formatJointAngles(angles) {
  if (!angles || !Array.isArray(angles)) return '--'
  return angles.map(a => `${a.toFixed(4)}°`).join(', ')
}

function formatEE(ee) {
  if (!ee) return '--'
  return `(${ee.x?.toFixed(3) ?? '?'}, ${ee.y?.toFixed(3) ?? '?'}, ${ee.z?.toFixed(3) ?? '?'})`
}
</script>
