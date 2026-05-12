<template>
  <el-container style="height: 100vh">
    <el-aside width="200px" class="tech-sidebar">
      <div class="tech-title">机器人控制</div>
      <el-menu :default-active="$route.path" router background-color="transparent" text-color="#6b7b8d" active-text-color="#00d4ff">
        <el-menu-item index="/"><el-icon><Monitor /></el-icon><span>状态监控</span></el-menu-item>
        <el-menu-item index="/commands"><el-icon><Operation /></el-icon><span>指令面板</span></el-menu-item>
        <el-menu-item index="/arm"><el-icon><SetUp /></el-icon><span>手臂运控</span></el-menu-item>
        <el-menu-item index="/navigation"><el-icon><MapLocation /></el-icon><span>导航</span></el-menu-item>
        <el-menu-item index="/ros2"><el-icon><Cpu /></el-icon><span>ROS2节点</span></el-menu-item>
        <el-menu-item index="/logs"><el-icon><Document /></el-icon><span>运行日志</span></el-menu-item>
      </el-menu>
    </el-aside>
    <el-main class="tech-main"><router-view /></el-main>
  </el-container>
</template>

<script setup>
import { Monitor, Operation, SetUp, MapLocation, Cpu, Document } from '@element-plus/icons-vue'
</script>
