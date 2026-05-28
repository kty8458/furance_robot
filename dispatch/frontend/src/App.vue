<template>
  <el-container style="height: 100vh">
    <el-aside width="200px" class="tech-sidebar">
      <div class="tech-title">调 度 系 统</div>
      <el-menu :default-active="$route.path" router background-color="transparent" text-color="#6b7b8d" active-text-color="#00d4ff">
        <el-menu-item index="/"><el-icon><Monitor /></el-icon><span>状态显示</span></el-menu-item>
        <el-menu-item index="/sampler"><el-icon><Setting /></el-icon><span>制样机控制</span></el-menu-item>
        <el-menu-item index="/tasks/editor"><el-icon><Edit /></el-icon><span>任务编排</span></el-menu-item>
        <el-menu-item index="/tasks/execution"><el-icon><VideoPlay /></el-icon><span>任务执行</span></el-menu-item>
        <el-menu-item index="/alarms"><el-icon><Bell /></el-icon><span>报警页面</span></el-menu-item>
        <el-menu-item index="/logs"><el-icon><Document /></el-icon><span>运行日志</span></el-menu-item>
      </el-menu>
    </el-aside>
    <el-main class="tech-main"><router-view /></el-main>
  </el-container>
</template>

<script setup>
import { Monitor, Setting, Edit, VideoPlay, Bell, Document } from '@element-plus/icons-vue'
</script>
