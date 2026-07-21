<template>
    <el-container style="height: 100vh">
        <el-aside width="200px" class="tech-sidebar">
            <div class="tech-title">机器人控制</div>
            <el-menu
                :default-active="$route.path"
                router
                background-color="transparent"
                text-color="#6b7b8d"
                active-text-color="#00d4ff"
            >
                <el-menu-item index="/"
                    ><el-icon><Monitor /></el-icon
                    ><span>状态监控</span></el-menu-item
                >
                <el-menu-item index="/arm"
                    ><el-icon><SetUp /></el-icon
                    ><span>上身运控</span></el-menu-item
                >
                <el-menu-item index="/navigation"
                    ><el-icon><MapLocation /></el-icon
                    ><span>导航</span></el-menu-item
                >
                <el-menu-item index="/camera"
                    ><el-icon><View /></el-icon><span>相机</span></el-menu-item
                >
                <el-menu-item index="/workflow"
                    ><el-icon><List /></el-icon
                    ><span>工作流</span></el-menu-item
                >
                <el-menu-item index="/ros2"
                    ><el-icon><Cpu /></el-icon
                    ><span>系统管理</span></el-menu-item
                >
            </el-menu>
            <!-- 当前工作流指示器 (固定在侧边栏底部) -->
            <div class="sidebar-wf-badge">
                <el-icon><Document /></el-icon>
                <span class="wf-name">{{ sharedWfState.currentWorkflowName || '未选择工作流' }}</span>
                <el-tag v-if="sharedWfState.execActive && sharedWfState.execLoop" type="warning" size="small" effect="dark" style="margin-left: auto">循环中</el-tag>
                <el-tag v-else-if="sharedWfState.execActive" type="success" size="small" effect="dark" style="margin-left: auto">执行中</el-tag>
                <el-tag v-else-if="sharedWfState.currentWorkflowName" type="info" size="small" style="margin-left: auto">未执行</el-tag>
            </div>
        </el-aside>
        <el-main class="tech-main"><router-view v-slot="{ Component }">
          <keep-alive :include="['WorkflowEditor', 'ArmControl']">
            <component :is="Component" />
          </keep-alive>
        </router-view></el-main>
        <ArmEnableFab />
    </el-container>
</template>

<script setup>
import {
    Monitor,
    SetUp,
    MapLocation,
    Cpu,
    List,
    View,
    Document
} from '@element-plus/icons-vue'
import ArmEnableFab from './components/ArmEnableFab.vue'
import { useSharedWorkflowState } from './composables/useSharedWorkflow'

const { state: sharedWfState } = useSharedWorkflowState()
</script>

<style>
.sidebar-wf-badge {
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    padding: 10px 14px;
    background: #0a1219;
    border-top: 1px solid #1e2d3d;
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: #00d4ff;
}
.sidebar-wf-badge .wf-name {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
</style>
