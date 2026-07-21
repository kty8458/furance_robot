<template>
  <div class="tech-page">
    <!-- ====== 上部: 工作流操作栏 (一行) ====== -->
    <el-card class="tech-card" style="margin-bottom: 12px">
      <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap">
        <el-icon><List /></el-icon>
        <span style="font-size: 14px; color: #e5e7eb">
          {{ currentWorkflow ? currentWorkflow.name : '未选择工作流' }}
        </span>
        <div style="flex: 1" />
        <el-button size="small" @click="showWorkflowListDialog = true">选择工作流</el-button>
        <el-button size="small" type="success" @click="createWorkflowPrompt">新建</el-button>
        <el-button size="small" @click="refreshList">刷新</el-button>
        <el-button v-if="currentWorkflow" size="small" type="primary" @click="openExecDialog" :disabled="!currentWorkflow.steps?.length || execResult?.active">
          执行
        </el-button>
        <el-button v-if="currentWorkflow" size="small" type="success" @click="saveWorkflow">保存</el-button>
        <el-button v-if="currentWorkflow" size="small" @click="duplicateWorkflow">复制工作流</el-button>
        <el-button v-if="execResult?.active" size="small" type="warning" @click="showResultDialog = true">查看进度</el-button>
        <el-button v-if="execResult?.active" size="small" type="danger" @click="handleCancel">停止</el-button>
      </div>
    </el-card>

    <!-- ====== 下部: 左侧添加步骤 + 右侧工作流编辑 ====== -->
    <el-row :gutter="16">
      <!-- 左侧: 添加步骤 (固定) -->
      <el-col :xs="24" :sm="6" :md="5">
        <el-card class="tech-card step-palette-card">
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
          <div style="margin-top: 10px; font-size: 11px; color: #6b7b8d">
            {{ selectedStepId ? '新步骤将插入到选中步骤下方' : '新步骤将添加到末尾' }}
          </div>
        </el-card>
      </el-col>

      <!-- 右侧: 工作流步骤列表 -->
      <el-col :xs="24" :sm="18" :md="19">
        <el-card class="tech-card">
          <template v-if="!currentWorkflow">
            <div style="color: #6b7b8d; text-align: center; padding: 40px 0">点击上方「选择工作流」或「新建」</div>
          </template>

          <template v-else-if="!currentWorkflow.steps?.length">
            <div style="color: #6b7b8d; text-align: center; padding: 40px 0">从左侧面板添加步骤</div>
          </template>

          <template v-else>
            <div style="margin-bottom: 8px; text-align: right">
              <el-button size="small" @click="toggleCollapseAll(true)">全部隐藏</el-button>
              <el-button size="small" @click="toggleCollapseAll(false)">全部展开</el-button>
            </div>
            <div class="step-list">
              <div v-for="(step, idx) in currentWorkflow.steps" :key="step.id"
                class="step-item" :class="{ 'step-selected': selectedStepId === step.id }"
                @click="selectedStepId = step.id">
                <div class="step-header">
                  <el-tag :type="stepTagType(step.type)" size="small">{{ stepTypeLabel(step.type) }}</el-tag>
                  <el-input v-model="step.label" placeholder="步骤名称" size="small" style="width: 160px; margin: 0 8px" @click.stop />
                  <el-button size="small" circle @click.stop="collapsedSteps[step.id] = !collapsedSteps[step.id]" :title="collapsedSteps[step.id] ? '展开' : '隐藏参数'">
                    {{ collapsedSteps[step.id] ? '⊕' : '⊖' }}
                  </el-button>
                  <el-button size="small" circle @click.stop="duplicateStep(idx)" title="复制此步骤">
                    <el-icon><CopyDocument /></el-icon>
                  </el-button>
                  <el-button size="small" :icon="ArrowUp" circle @click.stop="moveStepUp(idx)" :disabled="idx === 0" />
                  <el-button size="small" :icon="ArrowDown" circle @click.stop="moveStepDown(idx)" :disabled="idx === currentWorkflow.steps.length - 1" style="margin-left: 4px" />
                  <el-popconfirm title="删除此步骤？" @confirm="removeStep(idx)">
                    <template #reference>
                      <el-button size="small" type="danger" :icon="Delete" circle style="margin-left: 4px" @click.stop />
                    </template>
                  </el-popconfirm>
                </div>
                <div v-show="!collapsedSteps[step.id]" class="step-config">
                  <!-- move -->
                  <template v-if="step.type === 'move'">
                    <el-row :gutter="8" style="margin-bottom: 6px">
                      <el-col :span="12">
                        <div style="font-size: 11px; color: #6b7b8d">运动模式</div>
                        <el-select v-model="step.config.move_source" size="small" style="width: 100%">
                          <el-option label="调度系统" value="scheduler" />
                          <el-option label="手动选择" value="manual" />
                          <el-option label="定距离/定角度移动" value="move_with_params" />
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
                    <template v-else-if="step.config.move_source === 'move_with_params'">
                      <el-row :gutter="8" style="margin-bottom: 6px">
                        <el-col :span="24">
                          <div style="font-size: 11px; color: #6b7b8d">模式</div>
                          <el-radio-group v-model="step.config.mwp_mode" size="small">
                            <el-radio-button :value="1">定距离</el-radio-button>
                            <el-radio-button :value="2">定角度</el-radio-button>
                          </el-radio-group>
                        </el-col>
                      </el-row>
                      <el-row v-if="step.config.mwp_mode === 1" :gutter="8">
                        <el-col :span="8">
                          <div style="font-size: 10px; color: #6b7b8d">线速度 (m/s)</div>
                          <el-input-number v-model="step.config.linear_velocity" :min="-0.5" :max="0.5" :step="0.05" :precision="2" size="small" controls-position="right" style="width: 100%" />
                        </el-col>
                        <el-col :span="8">
                          <div style="font-size: 10px; color: #6b7b8d">距离 (m)</div>
                          <el-input-number v-model="step.config.target_distance" :min="0" :step="0.1" :precision="2" size="small" controls-position="right" style="width: 100%" />
                        </el-col>
                        <el-col :span="8">
                          <div style="font-size: 10px; color: #6b7b8d">侧偏角 (rad)</div>
                          <el-input-number v-model="step.config.slip_angle" :min="-2.14" :max="2.14" :step="0.1" :precision="2" size="small" controls-position="right" style="width: 100%" />
                        </el-col>
                      </el-row>
                      <el-row v-else :gutter="8">
                        <el-col :span="12">
                          <div style="font-size: 10px; color: #6b7b8d">角速度 (rad/s)</div>
                          <el-input-number v-model="step.config.angular_velocity" :min="-0.5" :max="0.5" :step="0.05" :precision="2" size="small" controls-position="right" style="width: 100%" />
                        </el-col>
                        <el-col :span="12">
                          <div style="font-size: 10px; color: #6b7b8d">角度 (rad)</div>
                          <el-input-number v-model="step.config.target_angle" :min="0" :max="3.14" :step="0.1" :precision="2" size="small" controls-position="right" style="width: 100%" />
                        </el-col>
                      </el-row>
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
                      <!-- Both-arm preset -->
                      <template v-if="step.config.arm === 'both'">
                        <!-- Toggle: use pre-composed both-arm preset vs combine two single-arm presets -->
                        <div style="margin-bottom: 8px">
                          <el-checkbox v-model="step.config.use_composed_preset" size="small" @change="onBothModeToggle(step)">
                            <span style="font-size: 11px; color: #9ca3af">使用已组合的双臂点位</span>
                          </el-checkbox>
                        </div>
                        <!-- Checked: single both-arm preset selector -->
                        <div v-if="step.config.use_composed_preset" style="margin-bottom: 6px">
                          <div style="font-size: 11px; color: #6b7b8d">双臂点位</div>
                          <el-select
                            v-model="step.config.preset_name"
                            size="small" style="width: 280px" filterable placeholder="选择双臂示教点"
                            @change="name => onPresetChange(step, name)"
                          >
                            <el-option
                              v-for="p in teachPresets.filter(t => t.arm === 'both' && t.method === 'moveJ')"
                              :key="'b_'+p.name" :label="p.name" :value="p.name"
                            />
                          </el-select>
                        </div>
                        <!-- Unchecked: two single-arm selectors + combine/sequential checkbox -->
                        <template v-else>
                          <el-row :gutter="8" style="margin-bottom: 8px">
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
                          <div v-if="step.config.method === 'moveJ'" style="margin-bottom: 6px">
                            <el-checkbox v-model="step.config.use_combined" size="small">
                              <span style="font-size: 11px; color: #9ca3af">合并双臂轨迹 (取消则先左后右分别执行)</span>
                            </el-checkbox>
                          </div>
                        </template>
                      </template>
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
                      <!-- 坐标模式 -->
                      <el-row :gutter="8" style="margin-bottom: 6px">
                        <el-col :span="12">
                          <div style="font-size: 11px; color: #6b7b8d">模式</div>
                          <el-select v-model="step.config.pose_mode" size="small" style="width: 100%"
                            @change="val => onPoseModeChange(step, val)">
                            <el-option label="手动输入" value="manual" />
                            <el-option label="当前末端" value="current_ee" />
                            <el-option label="关联视觉" value="vision" />
                          </el-select>
                        </el-col>
                        <el-col :span="12" v-if="step.config.pose_mode === 'vision'">
                          <div style="font-size: 11px; color: #6b7b8d">关联视觉步骤</div>
                          <el-select v-model="step.config.vision_step_label" size="small" style="width: 100%"
                            @change="label => onVisionStepLabelChange(step, label)">
                            <el-option v-for="vs in getPrecedingVisionLabels(idx)" :key="vs.label"
                              :label="vs.label || vs.id" :value="vs.label" />
                          </el-select>
                        </el-col>
                      </el-row>

                      <!-- 输入位姿 -->
                      <div style="font-size: 11px; color: #00d4ff; margin-bottom: 4px">── 输入位姿 ──</div>
                      <el-row :gutter="6" style="margin-bottom: 8px">
                        <el-col :span="4" v-for="(f, fi) in poseFields" :key="'in_'+fi">
                          <div style="font-size: 10px; color: #6b7b8d">{{ f }}</div>
                          <el-input
                            v-if="step.config.pose_mode === 'manual'"
                            v-model="step.config.position[f]"
                            :placeholder="f"
                            size="small"
                          />
                          <div v-else-if="step.config.pose_mode === 'current_ee'"
                            style="font-size: 11px; color: #00ff88; padding-top: 5px; font-style: italic">
                            当前末端
                          </div>
                          <div v-else-if="step.config.pose_mode === 'vision'"
                            style="font-size: 11px; color: #ffa500; padding-top: 5px; font-style: italic">
                            视觉输出
                          </div>
                        </el-col>
                      </el-row>

                      <!-- 偏移 -->
                      <div style="margin-bottom: 6px">
                        <el-checkbox v-model="step.config.enable_offset" size="small" @change="onOffsetToggle(step)">
                          <span style="font-size: 11px; color: #9ca3af">启用偏移</span>
                        </el-checkbox>
                      </div>
                      <template v-if="step.config.enable_offset">
                        <div style="font-size: 11px; color: #00d4ff; margin-bottom: 4px">── 偏移 ──</div>
                        <div style="margin-bottom: 6px">
                          <span style="font-size: 11px; color: #9ca3af; margin-right: 10px">参考系:</span>
                          <el-checkbox v-model="step.config.offset_ref_base" size="small"
                            :disabled="step.config.offset_ref_tool" @change="onOffsetRefChange(step, 'base')">
                            <span style="font-size: 11px">base_link</span>
                          </el-checkbox>
                          <el-checkbox v-model="step.config.offset_ref_tool" size="small"
                            :disabled="step.config.offset_ref_base" @change="onOffsetRefChange(step, 'tool')">
                            <span style="font-size: 11px">tool_link</span>
                          </el-checkbox>
                        </div>
                        <el-row :gutter="6">
                          <el-col :span="4" v-for="(f, fi) in poseFields" :key="'off_'+fi">
                            <div style="font-size: 10px; color: #6b7b8d">d{{ f }}</div>
                            <el-input v-model="step.config.offset[f]" :placeholder="'d'+f" size="small" />
                          </el-col>
                        </el-row>
                      </template>

                      <div style="font-size: 10px; color: #6b7b8d; margin-top: 4px">
                        参考坐标系: {{ step.config.reference_frame || 'base_link' }}
                      </div>
                      <el-input v-model="step.config.reference_frame" placeholder="base_link" size="small" style="width: 200px; margin-top: 4px" />
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
                          <el-option label="位置" value="position" />
                        </el-select>
                      </el-col>
                      <el-col :span="8">
                        <div style="font-size: 11px; color: #6b7b8d">力矩(0-100)</div>
                        <el-input-number v-model="step.config.force" :min="0" :max="100" :step="1" size="small" controls-position="right" style="width: 100%" />
                      </el-col>
                    </el-row>
                    <el-row v-if="step.config.action === 'position'" :gutter="8" style="margin-top: 6px">
                      <el-col :span="8">
                        <div style="font-size: 11px; color: #6b7b8d">位置(0-100)</div>
                        <el-input-number v-model="step.config.position" :min="0" :max="100" :step="1" size="small" controls-position="right" style="width: 100%" />
                      </el-col>
                    </el-row>
                  </template>

                  <!-- vision -->
                  <template v-if="step.type === 'vision'">
                    <el-row :gutter="8" style="margin-bottom: 6px">
                      <el-col :span="12">
                        <div style="font-size: 11px; color: #6b7b8d">相机</div>
                        <el-select v-model="step.config.camera_id" size="small" style="width: 100%">
                          <el-option
                            v-for="cam in cameraList"
                            :key="cam.id"
                            :label="`${cam.name} (${cam.id})`"
                            :value="cam.id"
                            :disabled="!cam.connected"
                          />
                        </el-select>
                      </el-col>
                      <el-col :span="12">
                        <div style="font-size: 11px; color: #6b7b8d">功能</div>
                        <el-select v-model="step.config.function" size="small" style="width: 100%">
                          <el-option label="二维码" value="qr_detect" />
                          <el-option label="视觉模型" value="vision_model" :disabled="true" />
                        </el-select>
                      </el-col>
                    </el-row>
                    <el-row :gutter="8" style="margin-bottom: 6px">
                      <el-col :span="12">
                        <div style="font-size: 11px; color: #6b7b8d">场景</div>
                        <el-select v-model="step.config.scene" size="small" style="width: 100%"
                          @visible-change="v => v && refreshSceneList()"
                          @change="val => { loadScenePoints(val); step.config.point_name = '' }">
                          <el-option v-for="s in sceneList" :key="s.scene_id"
                            :label="`${s.scene_id} (${s.description})`" :value="s.scene_id" />
                        </el-select>
                      </el-col>
                      <el-col :span="12">
                        <div style="font-size: 11px; color: #6b7b8d">标定点</div>
                        <el-select v-model="step.config.point_name" size="small" style="width: 100%"
                          @visible-change="v => v && step.config.scene && loadScenePoints(step.config.scene)">
                          <el-option v-for="p in (scenePoints[step.config.scene] || [])"
                            :key="p.name || p" :label="p.name || p" :value="p.name || p" />
                        </el-select>
                      </el-col>
                    </el-row>
                    <div style="font-size: 10px; color: #6b7b8d; margin-top: 4px">
                      输出: target_pose — 后续坐标模式用「关联视觉」引用
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

    <!-- 工作流列表弹窗 -->
    <el-dialog v-model="showWorkflowListDialog" title="工作流列表" width="500px">
      <el-form :inline="true" size="small" style="margin-bottom: 10px">
        <el-form-item>
          <el-input v-model="newWorkflowName" placeholder="工作流名称" style="width: 180px" @keyup.enter="createWorkflow" />
        </el-form-item>
        <el-form-item>
          <el-button type="success" size="small" @click="createWorkflow" :disabled="!newWorkflowName">新建</el-button>
        </el-form-item>
      </el-form>
      <el-table :data="workflows" border size="small" style="width: 100%" max-height="400" @row-click="row => { selectWorkflow(row); showWorkflowListDialog = false }" highlight-current-row>
        <el-table-column prop="name" label="名称" min-width="100" />
        <el-table-column label="步骤" width="60">
          <template #default="{ row }">{{ row.step_count }}</template>
        </el-table-column>
        <el-table-column label="操作" width="60">
          <template #default="{ row }">
            <el-popconfirm title="确定删除？" @confirm="deleteWorkflow(row.name)">
              <template #reference>
                <el-button type="danger" size="small" circle @click.stop><el-icon><Delete /></el-icon></el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

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
        <el-divider />
        <el-row :gutter="12" style="margin-bottom: 12px">
          <el-col :span="12">
            <div style="font-size: 11px; color: #6b7b8d; margin-bottom: 4px">起始步骤</div>
            <div style="font-size: 13px; color: #e5e7eb; padding-top: 4px">
              {{ execStartStep > 0 ? `从第 ${execStartStep + 1} 步开始 (${currentWorkflow?.steps?.[execStartStep]?.label || currentWorkflow?.steps?.[execStartStep]?.id || ''})` : '从头开始' }}
              <el-button v-if="selectedStepId" size="small" link type="primary" @click="execStartStep = currentWorkflow.steps.findIndex(s => s.id === selectedStepId)" style="margin-left: 8px">从选中步骤开始</el-button>
              <el-button v-if="execStartStep > 0" size="small" link @click="execStartStep = 0" style="margin-left: 4px">重置</el-button>
            </div>
          </el-col>
          <el-col :span="6">
            <div style="font-size: 11px; color: #6b7b8d; margin-bottom: 4px">循环执行</div>
            <el-switch v-model="execLoop" />
          </el-col>
          <el-col :span="6" v-if="execLoop">
            <div style="font-size: 11px; color: #6b7b8d; margin-bottom: 4px">循环间隔 (秒)</div>
            <el-input-number v-model="execLoopInterval" :min="0" :step="0.5" :precision="1" size="small" style="width: 100%" />
          </el-col>
        </el-row>
        <div style="display: flex; align-items: center; gap: 8px">
          <el-switch v-model="manualMode" />
          <span style="font-size: 13px; color: #e5e7eb">手动执行模式（每步等待确认）</span>
        </div>
        <div v-if="execStartStep > 0" style="margin-top: 8px; font-size: 11px; color: #ffa500">
          ⚠ 从中间步骤执行, 跳过的视觉步骤的输出将不可用
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
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag :type="statusTag(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="message" label="信息" min-width="160" show-overflow-tooltip />
        </el-table>
      </div>
      <template #footer>
        <el-button v-if="execResult?.manual_mode && execResult?.active && execResult?.waiting_for_next" type="success" @click="triggerNextStep">
          下一步
        </el-button>
        <el-button @click="showResultDialog = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
defineOptions({ name: 'WorkflowEditor' })
import { ref, reactive, onMounted, computed, watch, onActivated } from 'vue'
import { useSharedWorkflowState } from '../composables/useSharedWorkflow'
import { workflowApi } from '../api/workflow'
import { ElMessage, ElMessageBox } from 'element-plus'
import { List, Plus, Edit, Delete, ArrowUp, ArrowDown, CopyDocument } from '@element-plus/icons-vue'
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
const { state: sharedWfState, setWorkflow: setSharedWorkflow, setExecState: setSharedExecState } = useSharedWorkflowState()
const newWorkflowName = ref('')
const showExecDialog = ref(false)
const showResultDialog = ref(false)
const executing = ref(false)
const execResult = ref(null)
const manualMode = ref(false)   // 手动执行模式开关
const execStartStep = ref(0)     // 从第几步开始
const execLoop = ref(false)       // 循环执行
const execLoopInterval = ref(0) // 循环间隔秒
const selectedStepId = ref(null)  // 当前选中的步骤 ID (用于插入位置)
const showWorkflowListDialog = ref(false)  // 工作流列表弹窗
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
const cameraList = ref([])
const sceneList = ref([])
const scenePoints = ref({})  // {scene_id: [point names]}

let stepCounter = 0

// Vision steps preceding a given step index (constraint: only pick earlier steps)
function getPrecedingVisionSteps(currentIdx) {
  if (!currentWorkflow.value?.steps) return []
  return currentWorkflow.value.steps
    .filter((s, i) => s.type === 'vision' && i < currentIdx)
}

// Vision step labels (for the dropdown in pose mode)
function getPrecedingVisionLabels(currentIdx) {
  if (!currentWorkflow.value?.steps) return []
  return currentWorkflow.value.steps
    .filter((s, i) => s.type === 'vision' && i < currentIdx)
}

function onPoseModeChange(step, mode) {
  if (mode !== 'vision') step.config.vision_step_label = ''
  if (mode === 'manual') {
    step.config.position = {}
  } else if (mode === 'current_ee') {
    step.config.position = {}
  }
}

function onVisionStepLabelChange(step, label) {
  // The step label is used at execution time to reference the vision output
  step.config.vision_step_label = label
  step.config.position = {}
}

function onOffsetToggle(step) {
  if (!step.config.enable_offset) {
    step.config.offset = {}
  }
}

function onOffsetRefChange(step, ref) {
  if (ref === 'base') {
    step.config.offset_ref_tool = false
  } else {
    step.config.offset_ref_base = false
  }
}

// Move steps that use scheduler mode (need manual input at execution time)
const schedulerMoveSteps = computed(() => {
  if (!currentWorkflow.value?.steps) return []
  return currentWorkflow.value.steps.filter(s => s.type === 'move' && s.config.move_source === 'scheduler')
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
  loadCameraList()
  loadSceneList()
})

// keep-alive 激活时轻量刷新 (不重新加载完整工作流数据, 只刷新列表标题)
onActivated(() => {
  refreshList()
  // 如果当前有选中的工作流, 刷新示教点 (可能其他页面修改了)
  if (currentWorkflow.value) {
    loadTeachPresets()
  }
})

async function loadTeachPresets() {
  try {
    const wfName = currentWorkflow.value?.name
    const r = await armApi.teachList(wfName)
    const payload = r.data
    teachPresets.value = payload?.data || payload || []
  } catch {
    teachPresets.value = []
  }
}

async function loadCameraList() {
  try {
    const { cameraApi } = await import('../api/camera')
    const res = await cameraApi.list()
    cameraList.value = res.data || []
  } catch {
    cameraList.value = []
  }
}

async function loadSceneList() {
  try {
    const { cameraApi } = await import('../api/camera')
    const res = await cameraApi.scene('list')
    sceneList.value = res.data || []
  } catch { sceneList.value = [] }
}

async function loadScenePoints(sceneId) {
  if (!sceneId) { scenePoints.value[sceneId] = []; return }
  try {
    const { cameraApi } = await import('../api/camera')
    const res = await cameraApi.scene('get', sceneId)
    const data = res.data || {}
    scenePoints.value[sceneId] = (data.qr_transforms || []).map(p => ({
      name: p.name, arm: p.arm, qr_id: p.qr_id, marker_size: p.marker_size, stream_type: p.stream_type || 'color',
    }))
  } catch { scenePoints.value[sceneId] = [] }
}

async function refreshSceneList() {
  await loadSceneList()
  // 刷新当前选中的场景的点位
  for (const step of currentWorkflow.value?.steps || []) {
    if (step.type === 'vision' && step.config.scene) {
      await loadScenePoints(step.config.scene)
    }
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
  step.config.use_composed_preset = false
  if (step.config.arm === 'both') step.config.method = 'moveJ'
}

function onBothModeToggle(step) {
  // Clear presets when switching between composed vs separate mode
  step.config.preset_name = ''
  step.config.left_preset_name = ''
  step.config.right_preset_name = ''
  if (step.config.use_composed_preset) {
    step.config.method = 'moveJ'
    step.config.use_combined = true
  }
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

// 手动模式: 触发下一步
async function triggerNextStep() {
  if (!execResult.value?.execution_id) return
  try {
    await workflowApi.triggerNext(execResult.value.execution_id)
    ElMessage.success('已触发下一步')
  } catch (e) {
    ElMessage.error(e.message || '触发失败')
  }
}

function stepTagType(type) {
  const map = { move: '', upper_limb: 'success', upper_body: 'warning', gripper: 'danger', vision: 'info', sleep: '' }
  return map[type] || ''
}

// 折叠步骤详情 (隐藏参数, 仅保留类型+名称)
const collapsedSteps = ref({})  // {step_id: true}

function toggleCollapseAll(collapse) {
  if (!currentWorkflow.value?.steps) return
  for (const s of currentWorkflow.value.steps) {
    collapsedSteps.value[s.id] = collapse
  }
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
        if (s.type === 'move' && s.config.mwp_mode == null) s.config.mwp_mode = 1
        if (s.type === 'move' && s.config.linear_velocity == null) s.config.linear_velocity = 0.2
        if (s.type === 'move' && s.config.slip_angle == null) s.config.slip_angle = 0.0
        if (s.type === 'move' && s.config.angular_velocity == null) s.config.angular_velocity = 0.2
        if (s.type === 'move' && s.config.target_distance == null) s.config.target_distance = 1.0
        if (s.type === 'move' && s.config.target_angle == null) s.config.target_angle = 0.0
        if (s.type === 'upper_body') {
          s.config._waist = s.config.waist_angle != null
          s.config._ascend = s.config.ascend_pos != null
          s.config._head = s.config.head_angle != null
        }
        if (s.type === 'upper_limb' && !s.config.mode) s.config.mode = 'preset'
        if (s.type === 'upper_limb' && !s.config.method) s.config.method = 'moveJ'
        if (s.type === 'upper_limb' && !s.config.arm) s.config.arm = 'left'
        if (s.type === 'upper_limb' && s.config.use_combined == null) s.config.use_combined = true
        if (s.type === 'upper_limb' && s.config.use_composed_preset == null) s.config.use_composed_preset = false
        if (s.type === 'upper_limb' && !s.config.reference_frame) s.config.reference_frame = 'base_link'
        if (s.type === 'upper_limb' && !s.config.left_reference_frame) s.config.left_reference_frame = 'base_link'
        if (s.type === 'upper_limb' && !s.config.right_reference_frame) s.config.right_reference_frame = 'base_link'
        if (s.type === 'upper_limb' && !s.config.position) s.config.position = {}
        if (s.type === 'upper_limb' && !s.config.pose_mode) s.config.pose_mode = 'manual'
        if (s.type === 'upper_limb' && s.config.enable_offset == null) s.config.enable_offset = false
        if (s.type === 'upper_limb' && s.config.offset_ref_base == null) s.config.offset_ref_base = true
        if (s.type === 'upper_limb' && s.config.offset_ref_tool == null) s.config.offset_ref_tool = false
        if (s.type === 'upper_limb' && !s.config.offset) s.config.offset = {}
        if (s.type === 'gripper' && !s.config.arm) s.config.arm = 'left'
        if (s.type === 'gripper' && !s.config.action) s.config.action = 'open'
        if (s.type === 'gripper' && s.config.force == null) s.config.force = 0
        if (s.type === 'gripper' && s.config.position == null) s.config.position = 0
        if (s.type === 'vision' && !s.config.function) s.config.function = 'qr_detect'
        if (s.type === 'vision' && !s.config.scene) s.config.scene = ''
        if (s.type === 'vision' && !s.config.point_name) s.config.point_name = ''
        if (s.type === 'vision' && !s.config.camera_id) s.config.camera_id = cameraList.value.find(c => c.connected)?.id || 'head'
        if (s.type === 'sleep' && !s.config.duration) s.config.duration = 1
        stepCounter = Math.max(stepCounter, parseInt(s.id?.split('_').pop()) || 0)
      })
    }
    currentWorkflow.value = data
    setSharedWorkflow(data.name)
    // 重新编号所有步骤 (基于位置)
    renumberSteps()
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

async function saveWorkflow(opts = {}) {
  const silent = opts.silent === true
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
    if (!silent) ElMessage.success('保存成功')
  } catch (error) {
    if (!silent) ElMessage.error(error.message || '保存失败')
    throw error
  }
}

async function deleteWorkflow(name) {
  try {
    await workflowApi.delete(name)
    ElMessage.success('已删除')
    if (currentWorkflow.value?.name === name) {
      currentWorkflow.value = null
      setSharedWorkflow('')
    }
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
    move: {
      move_source: 'scheduler', map_name: '', point_name: '', path_type: 'NavigationPointTask',
      mwp_mode: 1, linear_velocity: 0.2, slip_angle: 0.0, angular_velocity: 0.2,
      target_distance: 1.0, target_angle: 0.0,
    },
    upper_limb: { mode: 'preset', arm: 'left', method: 'moveJ', preset_name: '', left_preset_name: '', right_preset_name: '', use_combined: true, use_composed_preset: false, reference_frame: 'base_link', left_reference_frame: 'base_link', right_reference_frame: 'base_link', position: {}, vision_source: '', left_vision_source: '', right_vision_source: '', pose_mode: 'manual', vision_step_label: '', enable_offset: false, offset_ref_base: true, offset_ref_tool: false, offset: {} },
    upper_body: { _waist: false, _ascend: false, _head: false, waist_angle: 300, waist_speed: 20, ascend_pos: 100, ascend_speed: 20, head_angle: 15, head_speed: 10 },
    gripper: { arm: 'left', action: 'open', force: 0, position: 0 },
    vision: { camera_id: cameraList.value.find(c => c.connected)?.id || 'head', function: 'qr_detect', scene: '', point_name: '' },
    sleep: { duration: 1 },
  }
  const newStep = {
    id: `step_${stepCounter}`,
    type,
    label: '',
    config: { ...defaults[type] },
  }
  // 插入到选中步骤下方, 否则添加到末尾
  if (selectedStepId.value) {
    const idx = currentWorkflow.value.steps.findIndex(s => s.id === selectedStepId.value)
    if (idx >= 0) {
      currentWorkflow.value.steps.splice(idx + 1, 0, newStep)
    } else {
      currentWorkflow.value.steps.push(newStep)
    }
  } else {
    currentWorkflow.value.steps.push(newStep)
  }
  renumberSteps()
  // 选中新添加的步骤 (它在数组中的位置)
  const newIdx = currentWorkflow.value.steps.findIndex(s =>
    s.type === type && s.label === '' && JSON.stringify(s.config) === JSON.stringify(newStep.config)
  )
  selectedStepId.value = newIdx >= 0 ? `step_${newIdx + 1}` : null
}

function duplicateStep(idx) {
  if (!currentWorkflow.value) return
  const src = currentWorkflow.value.steps[idx]
  if (!src) return
  const copy = JSON.parse(JSON.stringify(src))
  copy.label = (src.label || '') + '_副本'
  currentWorkflow.value.steps.push(copy)
  renumberSteps()
  ElMessage.success('已复制到末尾')
}

function createWorkflowPrompt() {
  ElMessageBox.prompt('请输入工作流名称', '新建工作流', {
    confirmButtonText: '新建',
    cancelButtonText: '取消',
  }).then(({ value }) => {
    if (!value) return
    newWorkflowName.value = value
    createWorkflow()
  }).catch(() => {})
}

async function duplicateWorkflow() {
  if (!currentWorkflow.value) return
  try {
    const { value } = await ElMessageBox.prompt('请输入新工作流名称', '复制工作流', {
      confirmButtonText: '复制',
      cancelButtonText: '取消',
      inputValue: currentWorkflow.value.name + '_副本',
    })
    if (!value) return
    const copy = JSON.parse(JSON.stringify(currentWorkflow.value))
    copy.name = value
    delete copy.id
    await workflowApi.save(value, copy)
    ElMessage.success(`已复制为 ${value}`)
    await refreshList()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e.message || '复制失败')
  }
}

function renumberSteps() {
  if (!currentWorkflow.value?.steps) return
  currentWorkflow.value.steps.forEach((s, i) => {
    s.id = `step_${i + 1}`
  })
}

function removeStep(idx) {
  currentWorkflow.value.steps.splice(idx, 1)
  renumberSteps()
}

function moveStepUp(idx) {
  if (idx === 0) return
  const steps = currentWorkflow.value.steps
  ;[steps[idx - 1], steps[idx]] = [steps[idx], steps[idx - 1]]
  renumberSteps()
}

function moveStepDown(idx) {
  const steps = currentWorkflow.value.steps
  if (idx >= steps.length - 1) return
  ;[steps[idx], steps[idx + 1]] = [steps[idx + 1], steps[idx]]
  renumberSteps()
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

function openExecDialog() {
  // 如果选中了步骤, 自动填充起始步骤
  if (selectedStepId.value && currentWorkflow.value?.steps) {
    const idx = currentWorkflow.value.steps.findIndex(s => s.id === selectedStepId.value)
    execStartStep.value = idx >= 0 ? idx : 0
  } else {
    execStartStep.value = 0
  }
  showExecDialog.value = true
}

async function executeWorkflow() {
  if (!currentWorkflow.value) return
  executing.value = true
  try {
    // 执行前自动保存，避免内存修改未持久化导致执行的是旧配置
    try {
      await saveWorkflow({ silent: true })
    } catch (e) {
      ElMessage.warning('自动保存失败，可能执行的是上次保存的配置')
    }

    // Prepopulate all steps with pending status
    execStepRows.value = currentWorkflow.value.steps.map(s => ({
      step_id: s.id,
      type: s.type,
      label: s.label,
      status: 'pending',
      message: '',
    }))

    // Build nav_params from scheduler-provided steps + manual steps
    // (move_with_params 模式不需要 nav_params, 参数已在 step.config 中)
    const navParams = currentWorkflow.value.steps
      .filter(s => s.type === 'move' && s.config.move_source !== 'move_with_params')
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
    const startRes = await workflowApi.execute(currentWorkflow.value.name, navParams, {
      manual_mode: manualMode.value,
      start_step_index: execStartStep.value,
      loop: execLoop.value,
      loop_interval: execLoopInterval.value,
    })
    const executionId = (startRes.data?.data || startRes.data)?.execution_id
    if (!executionId) {
      throw new Error('未获取到执行ID')
    }
    showExecDialog.value = false
    showResultDialog.value = true
    execResult.value = { active: true, step_results: [], message: '执行中...' }
    setSharedExecState(true, execLoop.value)
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
    setSharedExecState(false)
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
.step-palette-card {
  position: sticky;
  top: 12px;
}
.current-wf-badge {
  margin-top: 12px;
  padding: 10px 12px;
  background: #0d1a26;
  border: 1px solid #1e2d3d;
  border-radius: 6px;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #00d4ff;
  position: sticky;
  bottom: 0;
}
.step-item {
  border: 1px solid #2a3a4a;
  border-radius: 8px;
  padding: 10px;
  background: #0d1a26;
  cursor: pointer;
  transition: border-color 0.2s;
}
.step-item:hover {
  border-color: #3a5a7a;
}
.step-selected {
  border-color: #00d4ff !important;
  box-shadow: 0 0 8px rgba(0, 212, 255, 0.2);
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
