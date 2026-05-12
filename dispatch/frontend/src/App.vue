<template>
  <el-container style="height: 100vh">
    <el-aside width="200px" class="tech-sidebar">
      <div class="tech-title">调 度 系 统</div>
      <el-menu :default-active="$route.path" router background-color="transparent" text-color="#6b7b8d" active-text-color="#00d4ff">
        <el-menu-item index="/"><el-icon><Monitor /></el-icon><span>总览</span></el-menu-item>
        <el-menu-item index="/robot"><el-icon><Operation /></el-icon><span>机器人控制</span></el-menu-item>
        <el-menu-item index="/tasks"><el-icon><List /></el-icon><span>任务管理</span></el-menu-item>
        <el-menu-item index="/sampler"><el-icon><Setting /></el-icon><span>制样机</span></el-menu-item>
      </el-menu>
    </el-aside>
    <el-main class="tech-main"><router-view /></el-main>
  </el-container>
</template>

<script setup>
import { Monitor, Operation, List, Setting } from '@element-plus/icons-vue'
</script>
