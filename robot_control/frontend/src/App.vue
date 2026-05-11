<template>
  <el-container style="height: 100vh">
    <el-aside width="200px" style="background: #304156">
      <div style="color: #fff; padding: 20px; font-size: 16px; font-weight: bold; text-align: center">机器人控制</div>
      <el-menu :default-active="$route.path" router background-color="#304156" text-color="#bfcbd9" active-text-color="#409eff">
        <el-menu-item index="/"><el-icon><Monitor /></el-icon><span>状态监控</span></el-menu-item>
        <el-menu-item index="/commands"><el-icon><Operation /></el-icon><span>指令面板</span></el-menu-item>
        <el-menu-item index="/arm"><el-icon><SetUp /></el-icon><span>手臂运控</span></el-menu-item>
        <el-menu-item index="/navigation"><el-icon><MapLocation /></el-icon><span>导航</span></el-menu-item>
        <el-menu-item index="/ros2"><el-icon><Cpu /></el-icon><span>ROS2节点</span></el-menu-item>
        <el-menu-item index="/logs"><el-icon><Document /></el-icon><span>运行日志</span></el-menu-item>
      </el-menu>
    </el-aside>
    <el-main><router-view /></el-main>
  </el-container>
</template>

<script setup>
import { Monitor, Operation, SetUp, MapLocation, Cpu, Document } from '@element-plus/icons-vue'
</script>
