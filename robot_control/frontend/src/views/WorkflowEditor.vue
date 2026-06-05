<template>
  <div class="tech-page">
    <el-row :gutter="16">
      <!-- Left column: workflow list + step palette -->
      <el-col :xs="24" :sm="10" :md="8">
        <!-- Workflow list -->
        <el-card class="tech-card" style="margin-bottom: 16px">
          <template #header>
            <div class="tech-card-header">
              <el-icon><List /></el-icon>
              <span style="margin-left: 8px">工作流列表</span>
            </div>
          </template>
          <el-form :inline="true" size="small" style="margin-bottom: 10px">
            <el-form-item>
              <el-input v-model="newWorkflowName" placeholder="工序名称" style="width: 140px" @keyup.enter="createWorkflow" />
            </el-form-item>
            <el-form-item>
              <el-button type="success" size="small" @click="createWorkflow" :disabled="!newWorkflowName">新建</el-button>
            </el-form-item>
            <el-form-item>
              <el-button size="small" @click="refreshList">刷新</el-button>
            </el-form-item>
          </el-form>
          <el-table :data="workflows" border size="small" style="width: 100%" max-height="300" @row-click="selectWorkflow" highlight-current-row>
            <el-table-column prop="name" label="名称" min-width="80" />
            <el-table-column label="步骤" width="55">
              <template #default="{ row }">{{ row.step_count }}</template>
            </el-table-column>
            <el-table-column label="操作" width="55">
              <template #default="{ row }">
                <el-popconfirm title="确定删除？" @confirm="deleteWorkflow(row.name)">
                  <template #reference>
                    <el-button type="danger" size="small" circle><el-icon><Delete /></el-icon></el-button>
                  </template>
                </el-popconfirm>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <!-- Step type palette -->
        <el-card class="tech-card">
          <template #header>
            <div class="tech-card-header">
              <el-icon><Plus /></el-icon>
              <span style="margin-left: 8px">添加步骤</span>
            </div>
          </template>
          <div class="palette-grid">
            <div v-for="st in stepTypes" :key="st.type" class="palette-btn" @click="addStep(st.type)">
              <el-icon><component :is="st.icon" /></el-icon>
              <span class="palette-label">{{ st.label }}</span>
            </div>
          </div>
        </el-card>
      </el-col>

      <!-- Right column: step editor -->
      <el-col :xs="24" :sm="14" :md="16">
        <el-card class="tech-card">
          <template #header>
            <div class="tech-card-header">
              <el-icon><Edit /></el-icon>
              <span style="margin-left: 8px">
                {{ currentWorkflow ? currentWorkflow.name : '选择一个工作流' }}
              </span>
              <div style="flex: 1" />
              <el-button v-if="execResult?.active" size="small" type="warning" @click="showResultDialog = true" style="margin-right: 6px">
                查看进度
              </el-button>
              <el-button v-if="execResult?.active" size="small" type="danger" @click="handleCancel" style="margin-right: 6px">
                停止执行
              </el-button>
              <el-button v-if="currentWorkflow" size="small" type="primary" @click="showExecDialog = true" :disabled="!currentWorkflow.steps?.length || execResult?.active">
                执行
              </el-button>
              <el-button v-if="currentWorkflow" size="small" type="success" @click="saveWorkflow" style="margin-left: 6px">
                保存
              </el-button>
            </div>
          </template>

          <template v-if="!currentWorkflow">
            <div style="color: #6b7b8d; text-align: center; padding: 40px 0">选择左侧工作流或新建一个</div>
          </template>

          <template v-else-if="!currentWorkflow.steps?.length">
            <div style="color: #6b7b8d; text-align: center; padding: 40px 0">从左侧面板添加步骤</div>
          </template>

          <template v-else>
            <div class="step-list">
              <div v-for="(step, idx) in currentWorkflow.steps" :key="step.id" class="step-item">
                <div class="step-header">
                  <el-tag :type="stepTagType(step.type)" size="small">{{ stepTypeLabel(step.type) }}</el-tag>
                  <el-input v-model="step.label" placeholder="步骤名称" size="small" style="width: 160px; margin: 0 8px" />
                  <el-button size="small" :icon="ArrowUp" circle @click="moveStepUp(idx)" :disabled="idx === 0" />
                  <el-button size="small" :icon="ArrowDown" circle @click="moveStepDown(idx)" :disabled="idx === currentWorkflow.steps.length - 1" style="margin-left: 4px" />
                  <el-popconfirm title="删除此步骤？" @confirm="removeStep(idx)">
                    <template #reference>
                      <el-button size="small" type="danger" :icon="Delete" circle style="margin-left: 4px" />
                    </template>
                  </el-popconfirm>
                </div>
                <div class="step-config">
                  <!-- move -->
                  <template v-if="step.type === 'move'">
                    <el-row :gutter="8" style="margin-bottom: 6px">
                      <el-col :span="12">
                        <div style="font-size: 11px; color: #6b7b8d">点位来源</div>
                        <el-select v-model="step.config.move_source" size="small" style="width: 100%">
                          <el-option label="调度系统提供" value="scheduler" />
                          <el-option label="手动选择" value="manual" />
                        </el-select>
                      </el-col>
                    </el-row>
                    <template v-if="step.config.move_source === 'manual'">
                      <el-row :gutter="8" style="margin-bottom: 4px">
                        <el-col :span="12">
                          <div style="font-size: 10px; color: #6b7b8d">地图</div>
                          <el-select v-model="step.config.map_name" size="small" style="width: 100%" @change="map => onManualMapChange(step, map)" filterable>
                            <el-option v-for="m in navMaps" :key="m" :label="m" :value="m" />
                          </el-select>
                        </el-col>
                        <el-col :span="12">
                          <div style="font-size: 10px; color: #6b7b8d">类型</div>
                          <el-select v-model="step.config.path_type" size="small" style="width: 100%" @change="() => onManualMapChange(step, step.config.map_name)">
                            <el-option label="导航点" value="NavigationPointTask" />
                            <el-option label="录制路径" value="PlayPathTask" />
                            <el-option label="手绘路径" value="PlayGraphPathTask" />
                          </el-select>
                        </el-col>
                      </el-row>
                      <div style="font-size: 10px; color: #6b7b8d">点位/路径名</div>
                      <el-select v-model="step.config.point_name" size="small" style="width: 100%" filterable clearable placeholder="选择点位">
                        <el-option v-for="p in (manualNavPoints[step.id] || [])" :key="p" :label="p" :value="p" />
                      </el-select>
                    </template>
                    <template v-else>
                      <span style="font-size: 12px; color: #9ca3af">点位由调度系统在运行时提供</span>
                    </template>
                  </template>

                  <!-- upper_limb -->
                  <template v-if="step.type === 'upper_limb'">
                    <el-row :gutter="8" style="margin-bottom: 6px">
                      <el-col :span="8">
                        <div style="font-size: 11px; color: #6b7b8d">模式</div>
                        <el-select v-model="step.config.mode" size="small" style="width: 100%">
                          <el-option label="预设位" value="preset" />
                          <el-option label="坐标" value="pose" />
                        </el-select>
                      </el-col>
                      <el-col :span="8">
                        <div style="font-size: 11px; color: #6b7b8d">手臂</div>
                        <el-select v-model="step.config.arm" size="small" style="width: 100%" @change="onWfArmChange(step)">
                          <el-option label="左臂" value="left" />
                          <el-option label="右臂" value="right" />
                          <el-option label="双臂" value="both" />
                        </el-select>
                      </el-col>
                      <el-col :span="8">
                        <div style="font-size: 11px; color: #6b7b8d">方法</div>
                        <el-select v-model="step.config.method" size="small" style="width: 100%">
                          <el-option label="moveJ" value="moveJ" />
                          <el-option label="moveP" value="movep" />
                          <el-option label="moveL" value="moveL" />
                        </el-select>
                      </el-col>
                    </el-row>
                    <template v-if="step.config.mode === 'preset'">
                      <!-- Both-arm preset: two selectors side by side -->
                      <el-row v-if="step.config.arm === 'both'" :gutter="8" style="margin-bottom: 8px">
                        <el-col :span="12">
                          <div style="font-size: 11px; color: #6b7b8d">左臂点位</div>
                          <el-select
                            v-model="step.config.left_preset_name"
                            size="small" style="width: 100%" filterable placeholder="左臂示教点"
                            @change="name => onPresetSideChange(step, 'left', name)"
                          >
                            <el-option
                              v-for="p in teachPresets.filter(t => t.arm === 'left')"
                              :key="'l_'+p.name" :label="`${p.name} (${p.method || 'moveJ'})`" :value="p.name"
                            />
                          </el-select>
                        </el-col>
                        <el-col :span="12">
                          <div style="font-size: 11px; color: #6b7b8d">右臂点位</div>
                          <el-select
                            v-model="step.config.right_preset_name"
                            size="small" style="width: 100%" filterable placeholder="右臂示教点"
                            @change="name => onPresetSideChange(step, 'right', name)"
                          >
                            <el-option
                              v-for="p in teachPresets.filter(t => t.arm === 'right')"
                              :key="'r_'+p.name" :label="`${p.name} (${p.method || 'moveJ'})`" :value="p.name"
                            />
                          </el-select>
                        </el-col>
                      </el-row>
                      <!-- Single-arm preset: one selector -->
                      <div v-else>
                        <div style="font-size: 11px; color: #6b7b8d">预设位</div>
                        <el-select
                          v-model="step.config.preset_name"
                          size="small" style="width: 280px" filterable placeholder="选择示教点位"
                          @change="name => onPresetChange(step, name)"
                        >
                          <el-option
                            v-for="p in teachPresets.filter(t => t.arm === step.config.arm)"
                            :key="p.arm + '_' + p.name" :label="`${p.name} (${p.method || 'moveJ'})`" :value="p.name"
                          />
                        </el-select>
                      </div>
                    </template>
                    <template v-else>
                      <div style="font-size: 11px; color: #6b7b8d">参考坐标系</div>
                      <el-input v-model="step.config.reference_frame" placeholder="base_link" size="small" style="width: 200px; margin-bottom: 6px" />
                      <!-- Vision source selector (only steps before this one) -->
                      <div v-if="getPrecedingVisionSteps(idx).length" style="margin-bottom: 6px">
                        <div style="font-size: 11px; color: #00d4ff">关联视觉输出 (可选)</div>
                        <el-select v-model="step.config.vision_source" size="small" style="width: 200px" clearable placeholder="不关联" @change="val => onVisionSourceChange(step, val)">
                          <el-option v-for="vs in getPrecedingVisionSteps(idx)" :key="vs.id" :label="vs.label || vs.id" :value="vs.id" />
                        </el-select>
                      </div>
                      <el-row :gutter="6">
                        <el-col :span="4" v-for="(f, fi) in poseFields" :key="fi">
                          <div style="font-size: 10px; color: #6b7b8d">{{ f }}</div>
                          <el-input v-model="step.config.position[f]" :placeholder="f" size="small" />
                        </el-col>
                      </el-row>
                    </template>
                  </template>

                  <!-- upper_body -->
                  <template v-if="step.type === 'upper_body'">
                    <el-row :gutter="8">
                      <el-col :span="8">
                        <el-checkbox v-model="step.config._waist" label="腰部" size="small" style="margin-bottom: 4px" />
                        <el-input-number v-if="step.config._waist" v-model="step.config.waist_angle" :min="0" :max="600" size="small" controls-position="right" style="width: 100%" />
                      </el-col>
                      <el-col :span="8">
                        <el-checkbox v-model="step.config._ascend" label="偏转" size="small" style="margin-bottom: 4px" />
                        <el-input-number v-if="step.config._ascend" v-model="step.config.ascend_pos" :min="-180" :max="180" size="small" controls-position="right" style="width: 100%" />
                      </el-col>
                      <el-col :span="8">
                        <el-checkbox v-model="step.config._head" label="俯仰" size="small" style="margin-bottom: 4px" />
                        <el-input-number v-if="step.config._head" v-model="step.config.head_angle" :min="0" :max="35" size="small" controls-position="right" style="width: 100%" />
                      </el-col>
                    </el-row>
                  </template>

                  <!-- gripper -->
                  <template v-if="step.type === 'gripper'">
                    <el-row :gutter="8">
                      <el-col :span="8">
                        <div style="font-size: 11px; color: #6b7b8d">手臂</div>
                        <el-select v-model="step.config.arm" size="small" style="width: 100%">
                          <el-option label="左臂" value="left" />
                          <el-option label="右臂" value="right" />
                        </el-select>
                      </el-col>
                      <el-col :span="8">
                        <div style="font-size: 11px; color: #6b7b8d">动作</div>
                        <el-select v-model="step.config.action" size="small" style="width: 100%">
                          <el-option label="打开" value="open" />
                          <el-option label="闭合" value="close" />
                        </el-select>
                      </el-col>
                      <el-col :span="8">
                        <div style="font-size: 11px; color: #6b7b8d">力度</div>
                        <el-input-number v-model="step.config.force" :min="0" :step="0.1" size="small" controls-position="right" style="width: 100%" />
                      </el-col>
                    </el-row>
                  </template>

                  <!-- vision -->
                  <template v-if="step.type === 'vision'">
                    <el-row :gutter="8" style="margin-bottom: 6px">
                      <el-col :span="12">
                        <div style="font-size: 11px; color: #6b7b8d">相机</div>
                        <el-select v-model="step.config.camera_id" size="small" style="width: 100%">
                          <el-option label="相机 1" value="camera_1" />
                          <el-option label="相机 2" value="camera_2" />
                          <el-option label="相机 3" value="camera_3" />
                        </el-select>
                      </el-col>
                      <el-col :span="12">
                        <div style="font-size: 11px; color: #6b7b8d">场景标识</div>
                        <el-input v-model="step.config.scene" placeholder="例如: grasp_top" size="small" />
                      </el-col>
                    </el-row>
                    <div style="font-size: 10px; color: #6b7b8d; margin-top: 4px">
                      输出: grasp_pose — 后续坐标模式用「关联视觉输出」引用
                    </div>
                  </template>

                  <!-- sleep -->
                  <template v-if="step.type === 'sleep'">
                    <div style="font-size: 11px; color: #6b7b8d">延时 (秒)</div>
                    <el-input-number v-model="step.config.duration" :min="0.1" :step="0.1" size="small" controls-position="right" />
                  </template>
                </div>
              </div>
            </div>
          </template>
        </el-card>
      </el-col>
    </el-row>

    <!-- Execution dialog -->
    <el-dialog v-model="showExecDialog" title="执行工作流" width="600px">
      <div v-if="!currentWorkflow">无选中工作流</div>
      <template v-else>
        <div v-for="step in schedulerMoveSteps" :key="'nav-' + step.id" style="margin-bottom: 12px">
          <div style="font-size: 13px; color: #00d4ff; margin-bottom: 6px">{{ step.label || step.id }} (调度提供)</div>
          <el-row :gutter="8">
            <el-col :span="6">
              <div style="font-size: 11px; color: #6b7b8d">地图</div>
              <el-select v-model="execNavParams[step.id].map_name" size="small" style="width: 100%" @change="map => loadNavPoints(step.id, map)">
                <el-option v-for="m in maps" :key="m" :label="m" :value="m" />
              </el-select>
            </el-col>
            <el-col :span="6">
              <div style="font-size: 11px; color: #6b7b8d">类型</div>
              <el-select v-model="execNavParams[step.id].path_type" size="small" style="width: 100%" @change="() => loadNavPoints(step.id, execNavParams[step.id].map_name)">
                <el-option label="导航点" value="NavigationPointTask" />
                <el-option label="录制路径" value="PlayPathTask" />
                <el-option label="手绘路径" value="PlayGraphPathTask" />
              </el-select>
            </el-col>
            <el-col :span="12">
              <div style="font-size: 11px; color: #6b7b8d">点位/路径</div>
              <el-select v-model="execNavParams[step.id].point_name" size="small" style="width: 100%" filterable>
                <el-option v-for="p in execNavPoints[step.id]" :key="p" :label="p" :value="p" />
              </el-select>
            </el-col>
          </el-row>
        </div>
        <div v-if="manualMoveSteps.length" style="margin-top: 10px; padding: 8px; background: #0d2818; border-radius: 6px; font-size: 12px; color: #00ff88">
          {{ manualMoveSteps.length }} 个移动步骤使用预设点位，无需手动选择
        </div>
        <div v-if="!hasMoveSteps" style="color: #6b7b8d; padding: 12px 0">
          此工作流无导航步骤，可直接执行
        </div>
      </template>
      <template #footer>
        <el-button @click="showExecDialog = false">取消</el-button>
        <el-button type="primary" @click="executeWorkflow" :loading="executing">开始执行</el-button>
      </template>
    </el-dialog>

    <!-- Execution result dialog -->
    <el-dialog v-model="showResultDialog" title="执行结果" width="640px">
      <div v-if="execResult">
        <el-tag
          :type="execResult.active ? 'warning' : (execResult.success ? 'success' : 'danger')"
          size="large"
          style="margin-bottom: 12px"
        >
          {{ execResult.active ? '执行中...' : (execResult.success ? '执行成功' : '执行失败') }}
        </el-tag>
        <div v-if="execResult.message" style="margin-bottom: 12px; color: #9ca3af">{{ execResult.message }}</div>
        <el-table :data="execStepRows" border size="small">
          <el-table-column prop="step_id" label="步骤ID" width="100" />
          <el-table-column prop="type" label="类型" width="90" />
          <el-table-column prop="label" label="名称" min-width="120" />
          <el-table-column label="状态" width="80">
            <template #default="{ row }">
              <el-tag :type="statusTag(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="message" label="信息" min-width="160" show-overflow-tooltip />
        </el-table>
      </div>
      <template #footer>
        <el-button @click="showResultDialog = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed, watch } from 'vue'
import { workflowApi } from '../api/workflow'
import { ElMessage } from 'element-plus'
import { List, Plus, Edit, Delete, ArrowUp, ArrowDown } from '@element-plus/icons-vue'
import { navigationApi } from '../api/navigation'
import { armApi } from '../api/arm'

const stepTypes = [
  { type: 'move', label: '移动', icon: 'MapLocation' },
  { type: 'upper_limb', label: '上肢', icon: 'SetUp' },
  { type: 'upper_body', label: '上身', icon: 'Operation' },
  { type: 'gripper', label: '夹爪', icon: 'Scissor' },
  { type: 'vision', label: '视觉', icon: 'View' },
  { type: 'sleep', label: '延时', icon: 'Timer' },
]

const poseFields = ['x', 'y', 'z', 'roll', 'pitch', 'yaw']

const workflows = ref([])
const currentWorkflow = ref(null)
const newWorkflowName = ref('')
const showExecDialog = ref(false)
const showResultDialog = ref(false)
const executing = ref(false)
const execResult = ref(null)
const execStepRows = ref([])
const statusTagMap = { pending: 'info', running: 'warning', completed: 'success', failed: 'danger' }
const statusLabelMap = { pending: '待执行', running: '执行中', completed: '完成', failed: '失败' }
function statusTag(s) { return statusTagMap[s] || 'info' }
function statusLabel(s) { return statusLabelMap[s] || s }
const maps = ref([])
const navMaps = ref([])
const execNavParams = reactive({})
const execNavPoints = reactive({})
const manualNavPoints = reactive({})
const teachPresets = ref([])

let stepCounter = 0

// Vision steps preceding a given step index (constraint: only pick earlier steps)
function getPrecedingVisionSteps(currentIdx) {
  if (!currentWorkflow.value?.steps) return []
  return currentWorkflow.value.steps
    .filter((s, i) => s.type === 'vision' && i < currentIdx)
}

// Move steps that use scheduler mode (need manual input at execution time)
const schedulerMoveSteps = computed(() => {
  if (!currentWorkflow.value?.steps) return []
  return currentWorkflow.value.steps.filter(s => s.type === 'move' && s.config.move_source !== 'manual')
})

// Move steps that are pre-configured with manual nav points
const manualMoveSteps = computed(() => {
  if (!currentWorkflow.value?.steps) return []
  return currentWorkflow.value.steps.filter(s => s.type === 'move' && s.config.move_source === 'manual')
})

const hasMoveSteps = computed(() => {
  return currentWorkflow.value?.steps?.some(s => s.type === 'move')
})

onMounted(() => {
  refreshList()
  loadTeachPresets()
})

async function loadTeachPresets() {
  try {
    const r = await armApi.teachList()
    const payload = r.data
    teachPresets.value = payload?.data || payload || []
  } catch {
    teachPresets.value = []
  }
}

function onPresetChange(step, name) {
  const p = teachPresets.value.find(t => t.arm === step.config.arm && t.name === name)
  if (p) step.config.method = p.method || 'moveJ'
}

function onPresetSideChange(step, side, name) {
  // both-arm mode — auto set method to moveJ
  step.config.method = 'moveJ'
}

function onWfArmChange(step) {
  step.config.preset_name = ''
  step.config.left_preset_name = ''
  step.config.right_preset_name = ''
  if (step.config.arm === 'both') step.config.method = 'moveJ'
}

async function handleCancel() {
  if (!currentWorkflow.value) return
  try {
    await workflowApi.cancel(currentWorkflow.value.name)
    ElMessage.success('取消请求已发送')
  } catch (error) {
    ElMessage.error(error.message || '取消失败')
  }
}

function stepTagType(type) {
  const map = { move: '', upper_limb: 'success', upper_body: 'warning', gripper: 'danger', vision: 'info', sleep: '' }
  return map[type] || ''
}

function stepTypeLabel(type) {
  const st = stepTypes.find(s => s.type === type)
  return st ? st.label : type
}

function onVisionSourceChange(step, visionStepId) {
  if (!visionStepId) {
    step.config.position = {}
    return
  }
  const ref = `$${visionStepId}.grasp_pose`
  step.config.position = { x: `${ref}.x`, y: `${ref}.y`, z: `${ref}.z`, roll: `${ref}.roll`, pitch: `${ref}.pitch`, yaw: `${ref}.yaw` }
}

async function loadNavMaps() {
  try {
    const res = await navigationApi.getMaps()
    const data = res.data?.data || res.data || {}
    navMaps.value = data.data || data.maps || Object.keys(data) || []
  } catch {
    navMaps.value = []
  }
}

async function onManualMapChange(step, mapName) {
  if (!mapName) return
  const type = step.config.path_type || 'NavigationPointTask'
  try {
    let res
    if (type === 'NavigationPointTask') {
      res = await navigationApi.getPositions(mapName)
    } else if (type === 'PlayGraphPathTask') {
      res = await navigationApi.getGraphPaths(mapName)
    } else {
      res = await navigationApi.getRecordPaths(mapName)
    }
    const data = res.data?.data || res.data || {}
    const list = data.data || data.positions || data.paths || data || []
    manualNavPoints[step.id] = Array.isArray(list) ? list : Object.keys(list)
  } catch {
    manualNavPoints[step.id] = []
  }
}

async function refreshList() {
  try {
    const res = await workflowApi.list()
    workflows.value = res.data?.data || res.data || []
  } catch {
    ElMessage.error('获取工作流列表失败')
  }
}

async function selectWorkflow(row) {
  try {
    const res = await workflowApi.get(row.name)
    const data = res.data?.data || res.data
    if (data.steps) {
      data.steps.forEach(s => {
        if (s.type === 'move' && !s.config.move_source) s.config.move_source = 'scheduler'
        if (s.type === 'move' && !s.config.path_type) s.config.path_type = 'NavigationPointTask'
        if (s.type === 'upper_body') {
          s.config._waist = s.config.waist_angle != null
          s.config._ascend = s.config.ascend_pos != null
          s.config._head = s.config.head_angle != null
        }
        if (s.type === 'upper_limb' && !s.config.mode) s.config.mode = 'preset'
        if (s.type === 'upper_limb' && !s.config.method) s.config.method = 'moveJ'
        if (s.type === 'upper_limb' && !s.config.arm) s.config.arm = 'left'
        if (s.type === 'upper_limb' && !s.config.reference_frame) s.config.reference_frame = 'base_link'
        if (s.type === 'upper_limb' && !s.config.left_reference_frame) s.config.left_reference_frame = 'base_link'
        if (s.type === 'upper_limb' && !s.config.right_reference_frame) s.config.right_reference_frame = 'base_link'
        if (s.type === 'upper_limb' && !s.config.position) s.config.position = {}
        if (s.type === 'gripper' && !s.config.arm) s.config.arm = 'left'
        if (s.type === 'gripper' && !s.config.action) s.config.action = 'open'
        if (s.type === 'gripper' && s.config.force == null) s.config.force = 0
        if (s.type === 'vision' && !s.config.scene) s.config.scene = ''
        if (s.type === 'vision' && !s.config.camera_id) s.config.camera_id = 'camera_1'
        if (s.type === 'sleep' && !s.config.duration) s.config.duration = 1
        stepCounter = Math.max(stepCounter, parseInt(s.id?.split('_').pop()) || 0)
      })
    }
    currentWorkflow.value = data
    // Load nav maps for manual move step dropdowns
    await loadNavMaps()
    // Pre-populate nav points for existing manual move steps
    const steps = data.steps || []
    for (const s of steps) {
      if (s.type === 'move' && s.config.move_source === 'manual' && s.config.map_name) {
        await onManualMapChange(s, s.config.map_name)
      }
    }
  } catch {
    ElMessage.error('加载工作流失败')
  }
}

async function createWorkflow() {
  if (!newWorkflowName.value) return
  try {
    await workflowApi.save(newWorkflowName.value, { name: newWorkflowName.value, steps: [], description: '' })
    ElMessage.success('工作流已创建')
    newWorkflowName.value = ''
    await refreshList()
  } catch (error) {
    ElMessage.error(error.message || '创建失败')
  }
}

async function saveWorkflow() {
  if (!currentWorkflow.value) return
  try {
    const wf = JSON.parse(JSON.stringify(currentWorkflow.value))
    wf.steps.forEach(s => {
      if (s.type === 'upper_body') {
        const hadWaist = s.config._waist
        const hadAscend = s.config._ascend
        const hadHead = s.config._head
        delete s.config._waist
        delete s.config._ascend
        delete s.config._head
        if (!hadWaist) delete s.config.waist_angle
        if (!hadAscend) delete s.config.ascend_pos
        if (!hadHead) delete s.config.head_angle
      }
      // Clean vision_source (UI-only helper)
      if (s.type === 'upper_limb') {
        delete s.config.vision_source
      }
    })
    await workflowApi.update(wf.name, wf)
    ElMessage.success('保存成功')
  } catch (error) {
    ElMessage.error(error.message || '保存失败')
  }
}

async function deleteWorkflow(name) {
  try {
    await workflowApi.delete(name)
    ElMessage.success('已删除')
    if (currentWorkflow.value?.name === name) currentWorkflow.value = null
    await refreshList()
  } catch (error) {
    ElMessage.error(error.message || '删除失败')
  }
}

function addStep(type) {
  if (!currentWorkflow.value) {
    ElMessage.warning('请先选择或创建工作流')
    return
  }
  stepCounter++
  const defaults = {
    move: { move_source: 'scheduler', map_name: '', point_name: '', path_type: 'NavigationPointTask' },
    upper_limb: { mode: 'preset', arm: 'left', method: 'moveJ', preset_name: '', left_preset_name: '', right_preset_name: '', reference_frame: 'base_link', left_reference_frame: 'base_link', right_reference_frame: 'base_link', position: {}, vision_source: '', left_vision_source: '', right_vision_source: '' },
    upper_body: { _waist: false, _ascend: false, _head: false, waist_angle: 300, waist_speed: 20, ascend_pos: 100, ascend_speed: 20, head_angle: 15, head_speed: 10 },
    gripper: { arm: 'left', action: 'open', force: 0 },
    vision: { camera_id: 'camera_1', scene: '' },
    sleep: { duration: 1 },
  }
  currentWorkflow.value.steps.push({
    id: `step_${stepCounter}`,
    type,
    label: '',
    config: { ...defaults[type] },
  })
}

function removeStep(idx) {
  currentWorkflow.value.steps.splice(idx, 1)
}

function moveStepUp(idx) {
  if (idx === 0) return
  const steps = currentWorkflow.value.steps
  ;[steps[idx - 1], steps[idx]] = [steps[idx], steps[idx - 1]]
}

function moveStepDown(idx) {
  const steps = currentWorkflow.value.steps
  if (idx >= steps.length - 1) return
  ;[steps[idx], steps[idx + 1]] = [steps[idx + 1], steps[idx]]
}

async function loadMaps() {
  try {
    const res = await navigationApi.getMaps()
    const data = res.data?.data || res.data || {}
    maps.value = data.data || data.maps || Object.keys(data) || []
  } catch {
    maps.value = []
  }
}

async function loadNavPoints(stepId, mapName) {
  if (!mapName) return
  const params = execNavParams[stepId]
  const type = params.path_type
  try {
    let res
    if (type === 'NavigationPointTask') {
      res = await navigationApi.getPositions(mapName)
    } else if (type === 'PlayGraphPathTask') {
      res = await navigationApi.getGraphPaths(mapName)
    } else {
      res = await navigationApi.getRecordPaths(mapName)
    }
    const data = res.data?.data || res.data || {}
    const list = data.data || data.positions || data.paths || data || []
    execNavPoints[stepId] = Array.isArray(list) ? list : Object.keys(list)
  } catch {
    execNavPoints[stepId] = []
  }
}

async function executeWorkflow() {
  if (!currentWorkflow.value) return
  executing.value = true
  try {
    // Prepopulate all steps with pending status
    execStepRows.value = currentWorkflow.value.steps.map(s => ({
      step_id: s.id,
      type: s.type,
      label: s.label,
      status: 'pending',
      message: '',
    }))

    // Build nav_params from scheduler-provided steps + manual steps
    const navParams = currentWorkflow.value.steps
      .filter(s => s.type === 'move')
      .map(s => {
        if (s.config.move_source === 'manual') {
          return {
            step_id: s.id,
            map_name: s.config.map_name || '',
            point_name: s.config.point_name || '',
            path_type: s.config.path_type || 'NavigationPointTask',
          }
        }
        const np = execNavParams[s.id] || {}
        return {
          step_id: s.id,
          map_name: np.map_name || '',
          point_name: np.point_name || '',
          path_type: np.path_type || 'NavigationPointTask',
        }
      })
    const startRes = await workflowApi.execute(currentWorkflow.value.name, navParams)
    const executionId = (startRes.data?.data || startRes.data)?.execution_id
    if (!executionId) {
      throw new Error('未获取到执行ID')
    }
    showExecDialog.value = false
    showResultDialog.value = true
    execResult.value = { active: true, step_results: [], message: '执行中...' }
    execStepRows.value[0].status = 'running'

    // Poll until active=false, updating steps as results arrive
    while (true) {
      await new Promise(r => setTimeout(r, 1000))
      const statusRes = await workflowApi.getExecution(executionId)
      const state = statusRes.data?.data || statusRes.data
      execResult.value = state

      // Merge backend step_results into execStepRows
      if (state.step_results && state.step_results.length) {
        const resultMap = {}
        state.step_results.forEach(r => { resultMap[r.step_id] = r })
        for (let i = 0; i < execStepRows.value.length; i++) {
          const row = execStepRows.value[i]
          const result = resultMap[row.step_id]
          if (result) {
            row.status = result.success ? 'completed' : 'failed'
            row.message = result.message
            // Mark next step as running
            if (result.success && i + 1 < execStepRows.value.length) {
              execStepRows.value[i + 1].status = 'running'
            }
          }
        }
      }

      if (!state.active) break
    }
  } catch (error) {
    ElMessage.error(error.message || '执行失败')
  } finally {
    executing.value = false
  }
}

// Init exec nav params for scheduler-mode move steps when showing dialog
watch(showExecDialog, async (val) => {
  if (val && currentWorkflow.value) {
    await loadMaps()
    schedulerMoveSteps.value.forEach(s => {
      if (!execNavParams[s.id]) {
        execNavParams[s.id] = { map_name: '', point_name: '', path_type: 'NavigationPointTask' }
      }
    })
  }
})
</script>

<style scoped>
.palette-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.palette-btn {
  flex: 1 1 calc(50% - 6px);
  min-width: 90px;
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 8px 10px;
  border: 1px solid #2a3a4a;
  border-radius: 6px;
  background: #0d1a26;
  color: #6b7b8d;
  cursor: pointer;
  transition: all 0.2s;
  user-select: none;
  font-size: 13px;
}
.palette-btn:hover {
  border-color: #00d4ff;
  color: #00d4ff;
  background: #0a1a2e;
}
.palette-label {
  white-space: nowrap;
}
.step-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.step-item {
  border: 1px solid #2a3a4a;
  border-radius: 8px;
  padding: 10px;
  background: #0d1a26;
}
.step-header {
  display: flex;
  align-items: center;
  margin-bottom: 8px;
}
.step-config {
  padding-left: 4px;
}
</style>
