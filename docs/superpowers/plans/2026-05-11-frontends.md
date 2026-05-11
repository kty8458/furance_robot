# 前端页面 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现机器人控制系统和调度系统的前端Vue 3页面，功能性优先，工业风格

**Architecture:** Vue 3 + Vite，使用Element Plus组件库快速搭建工业风格UI。页面通过HTTP API与后端通讯，日志和状态通过WebSocket实时更新。

**Tech Stack:** Vue 3, Vite, Element Plus, axios, Vue Router

---

## 机器人控制系统前端

### File Structure

```
robot_control/frontend/
├── package.json
├── vite.config.js
├── index.html
├── src/
│   ├── main.js
│   ├── App.vue
│   ├── router.js
│   ├── api/
│   │   ├── index.js           # axios实例
│   │   ├── robot.js           # 机器人指令API
│   │   ├── arm.js             # 手臂运控+示教API
│   │   ├── navigation.js      # 导航API
│   │   └── ros2.js            # ROS2节点管理API
│   ├── composables/
│   │   ├── useStatus.js       # WebSocket状态订阅
│   │   └── useLogs.js         # WebSocket日志订阅
│   └── views/
│       ├── Dashboard.vue      # 状态监控总览
│       ├── Commands.vue       # 指令面板
│       ├── ArmControl.vue     # 手臂运控+示教
│       ├── Navigation.vue     # 导航(地图/点位)
│       ├── Ros2Nodes.vue      # ROS2节点管理
│       └── Logs.vue           # 运行日志
```

---

### Task R1: 项目初始化和基础设施

**Files:**
- Modify: `robot_control/frontend/package.json`
- Create: `vite.config.js`
- Create: `index.html`
- Create: `src/main.js`
- Create: `src/App.vue`
- Create: `src/router.js`
- Create: `src/api/index.js`

- [ ] **Step 1: 更新package.json添加依赖**

```json
{
  "name": "robot-control-frontend",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "vue": "^3.4",
    "vue-router": "^4.3",
    "element-plus": "^2.7",
    "axios": "^1.7"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^5.0",
    "vite": "^5.4"
  }
}
```

- [ ] **Step 2: 创建vite.config.js**

```js
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 3000,
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': { target: 'ws://localhost:8000', ws: true },
    },
  },
})
```

- [ ] **Step 3: 创建index.html**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>机器人控制系统</title>
</head>
<body>
  <div id="app"></div>
  <script type="module" src="/src/main.js"></script>
</body>
</html>
```

- [ ] **Step 4: 创建src/main.js**

```js
import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import App from './App.vue'
import router from './router'

createApp(App).use(ElementPlus).use(router).mount('#app')
```

- [ ] **Step 5: 创建src/App.vue**

```vue
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
```

- [ ] **Step 6: 创建src/router.js**

```js
import { createRouter, createWebHistory } from 'vue-router'
import Dashboard from './views/Dashboard.vue'
import Commands from './views/Commands.vue'
import ArmControl from './views/ArmControl.vue'
import Navigation from './views/Navigation.vue'
import Ros2Nodes from './views/Ros2Nodes.vue'
import Logs from './views/Logs.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: Dashboard },
    { path: '/commands', component: Commands },
    { path: '/arm', component: ArmControl },
    { path: '/navigation', component: Navigation },
    { path: '/ros2', component: Ros2Nodes },
    { path: '/logs', component: Logs },
  ],
})
```

- [ ] **Step 7: 创建src/api/index.js**

```js
import axios from 'axios'

const api = axios.create({ baseURL: '/api/v1' })

export default api
```

- [ ] **Step 8: 安装依赖并验证构建**

Run: `cd robot_control/frontend && npm install && npm run build`
Expected: build succeeds

- [ ] **Step 9: Commit**

```bash
git add robot_control/frontend/
git commit -m "feat(robot-control-frontend): initialize Vue 3 project with Element Plus"
```

---

### Task R2: API层和WebSocket Composables

**Files:**
- Create: `src/api/robot.js`
- Create: `src/api/arm.js`
- Create: `src/api/navigation.js`
- Create: `src/api/ros2.js`
- Create: `src/composables/useStatus.js`
- Create: `src/composables/useLogs.js`

- [ ] **Step 1: 创建API模块**

`src/api/robot.js`:
```js
import api from '.'

const ROBOT_ID = 'robot_001'

export const robotApi = {
  home: () => api.post(`/robot/${ROBOT_ID}/home`),
  grab: (target) => api.post(`/robot/${ROBOT_ID}/grab`, { target }),
  place: (target) => api.post(`/robot/${ROBOT_ID}/place`, { target }),
  gripper: (arm, action, force) => api.post(`/robot/${ROBOT_ID}/gripper`, { arm, action, force }),
  lift: (direction, height) => api.post(`/robot/${ROBOT_ID}/lift`, { direction, height }),
  charge: (action) => api.post(`/robot/${ROBOT_ID}/charge`, { action }),
  enable: (enable, clearError) => api.post(`/robot/${ROBOT_ID}/enable`, { enable, clear_error: clearError }),
}
```

`src/api/arm.js`:
```js
import api from '.'

const ROBOT_ID = 'robot_001'

export const armApi = {
  move: (params) => api.post(`/robot/${ROBOT_ID}/arm/move`, params),
  teachSave: (arm, name) => api.post(`/robot/${ROBOT_ID}/arm/teach/save`, { arm, name }),
  teachList: () => api.get(`/robot/${ROBOT_ID}/arm/teach/list`),
  teachExec: (arm, name) => api.post(`/robot/${ROBOT_ID}/arm/teach/exec`, { arm, name }),
  teachDelete: (name) => api.delete(`/robot/${ROBOT_ID}/arm/teach/${name}`),
}
```

`src/api/navigation.js`:
```js
import api from '.'

export const navigationApi = {
  getMaps: () => api.get('/maps'),
  getWaypoints: (mapId) => api.get(`/maps/${mapId}/waypoints`),
  move: (mapId, waypointId, speed) => api.post('/robot/robot_001/move', { map_id: mapId, waypoint_id: waypointId, speed }),
}
```

`src/api/ros2.js`:
```js
import api from '.'

export const ros2Api = {
  listNodes: () => api.get('/ros2/nodes'),
  startNode: (name) => api.post(`/ros2/nodes/${name}/start`),
  stopNode: (name) => api.post(`/ros2/nodes/${name}/stop`),
  nodeStatus: (name) => api.get(`/ros2/nodes/${name}/status`),
}
```

- [ ] **Step 2: 创建WebSocket composables**

`src/composables/useStatus.js`:
```js
import { ref, onMounted, onUnmounted } from 'vue'

export function useStatus() {
  const status = ref(null)
  const connected = ref(false)
  let ws = null
  let reconnectTimer = null

  function connect() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    ws = new WebSocket(`${protocol}//${location.host}/ws/v1/status`)
    ws.onopen = () => { connected.value = true }
    ws.onclose = () => {
      connected.value = false
      reconnectTimer = setTimeout(connect, 5000)
    }
    ws.onmessage = (event) => {
      const frame = JSON.parse(event.data)
      if (frame.type === 'status') status.value = frame.payload
    }
  }

  onMounted(connect)
  onUnmounted(() => {
    if (ws) ws.close()
    if (reconnectTimer) clearTimeout(reconnectTimer)
  })

  return { status, connected }
}
```

`src/composables/useLogs.js`:
```js
import { ref, onMounted, onUnmounted } from 'vue'

export function useLogs() {
  const logs = ref([])
  const connected = ref(false)
  const maxLogs = 1000
  let ws = null
  let reconnectTimer = null

  function connect() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    ws = new WebSocket(`${protocol}//${location.host}/ws/v1/logs`)
    ws.onopen = () => { connected.value = true }
    ws.onclose = () => {
      connected.value = false
      reconnectTimer = setTimeout(connect, 5000)
    }
    ws.onmessage = (event) => {
      const frame = JSON.parse(event.data)
      if (frame.type === 'log') {
        logs.value.push(frame.payload)
        if (logs.value.length > maxLogs) logs.value.splice(0, logs.value.length - maxLogs)
      }
    }
  }

  function clearLogs() { logs.value = [] }

  onMounted(connect)
  onUnmounted(() => {
    if (ws) ws.close()
    if (reconnectTimer) clearTimeout(reconnectTimer)
  })

  return { logs, connected, clearLogs }
}
```

- [ ] **Step 3: Commit**

```bash
git add robot_control/frontend/src/
git commit -m "feat(robot-control-frontend): add API modules and WebSocket composables"
```

---

### Task R3: 控制系统页面 — Dashboard + Commands

**Files:**
- Create: `src/views/Dashboard.vue`
- Create: `src/views/Commands.vue`

- [ ] **Step 1: 创建Dashboard.vue** — 状态监控总览，显示位置、电量、夹爪、手臂、任务状态

Dashboard显示: 位置(x,y,theta)、当前地图、电量+充电状态、使能状态、升降高度、左右夹爪状态+力矩、左右手臂状态+关节角度、任务状态、ROS2节点状态。使用el-card + el-descriptions布局。

- [ ] **Step 2: 创建Commands.vue** — 指令面板，所有机器人控制按钮

Commands包含: 归零按钮、抓取(输入target)、放置(输入target)、夹爪(选择左/右、开/闭、力矩)、升降(方向+高度)、充电(开始/停止)、使能+清错。每个指令组用el-card包裹，按钮用el-button。

- [ ] **Step 3: Commit**

```bash
git add robot_control/frontend/src/views/
git commit -m "feat(robot-control-frontend): add Dashboard and Commands views"
```

---

### Task R4: 控制系统页面 — ArmControl + Navigation + Ros2Nodes + Logs

**Files:**
- Create: `src/views/ArmControl.vue`
- Create: `src/views/Navigation.vue`
- Create: `src/views/Ros2Nodes.vue`
- Create: `src/views/Logs.vue`

- [ ] **Step 1: 创建ArmControl.vue**

分两区: 上方手臂运控(选择左/右臂、运动方法movep/moveL/moveJ、关节角度/位姿输入、坐标系、执行按钮)，下方示教管理(保存当前角度/预设位列表/执行预设位/删除预设位)。

- [ ] **Step 2: 创建Navigation.vue**

选择地图→显示导航点列表→选择导航点+输入速度→移动按钮。

- [ ] **Step 3: 创建Ros2Nodes.vue**

节点列表表格(名称+状态)+启动/停止按钮。

- [ ] **Step 4: 创建Logs.vue**

使用useLogs composable获取实时日志，el-table显示(level颜色区分: debug=info, warn=warning, error=danger)，过滤(level/source/关键字搜索)，清空按钮。

- [ ] **Step 5: 构建验证**

Run: `cd robot_control/frontend && npm run build`
Expected: build succeeds

- [ ] **Step 6: Commit**

```bash
git add robot_control/frontend/src/views/
git commit -m "feat(robot-control-frontend): add ArmControl, Navigation, Ros2Nodes, Logs views"
```

---

## 调度系统前端

### File Structure

```
dispatch/frontend/
├── package.json
├── vite.config.js
├── index.html
├── src/
│   ├── main.js
│   ├── App.vue
│   ├── router.js
│   ├── api/
│   │   ├── index.js
│   │   ├── robot.js
│   │   ├── task.js
│   │   ├── sampler.js
│   │   └── navigation.js
│   └── views/
│       ├── Dashboard.vue       # 总览(机器人+制样机状态)
│       ├── RobotControl.vue    # 机器人指令下发
│       ├── Tasks.vue           # 任务管理(模板+执行+历史)
│       └── Sampler.vue         # 制样机控制+状态
```

---

### Task D1: 调度系统前端项目初始化

与R1类似，创建Vue 3 + Element Plus + Vue Router项目，侧边栏菜单包含: 总览、机器人控制、任务管理、制样机。

vite.config.js proxy指向 `http://localhost:8000`。

- [ ] **实现并Commit**

```bash
git add dispatch/frontend/
git commit -m "feat(dispatch-frontend): initialize Vue 3 project with Element Plus"
```

---

### Task D2: 调度系统API层

`src/api/robot.js` — 转发机器人控制指令(home, grab, place, gripper, lift, charge, enable) + 获取状态
`src/api/task.js` — 任务模板列表、执行任务、执行记录列表、执行详情、取消任务
`src/api/sampler.js` — 制样机指令(start/stop/query)、状态查询
`src/api/navigation.js` — 地图列表、导航点列表(代理)

- [ ] **实现并Commit**

```bash
git add dispatch/frontend/src/api/
git commit -m "feat(dispatch-frontend): add API modules"
```

---

### Task D3: 调度系统页面 — 全部视图

**Dashboard.vue**: 机器人状态卡片(位置、电量、任务状态) + 制样机状态卡片(状态、进度)
**RobotControl.vue**: 指令下发面板(与控制系统Commands类似，但通过调度系统代理)
**Tasks.vue**: 上方任务模板列表+执行按钮(选择机器人)，下方执行历史表格(含步骤日志)
**Sampler.vue**: 制样机状态展示+控制按钮(开始/停止/查询)

- [ ] **构建验证**

Run: `cd dispatch/frontend && npm run build`
Expected: build succeeds

- [ ] **Commit**

```bash
git add dispatch/frontend/src/
git commit -m "feat(dispatch-frontend): add all views (Dashboard, RobotControl, Tasks, Sampler)"
```

---

## Self-Review

**1. Spec coverage:**
- 控制系统页面: 状态监控 ✓、指令面板 ✓、手臂运控+示教 ✓、导航 ✓、ROS2节点管理 ✓、运行日志 ✓
- 调度系统页面: 总览 ✓、机器人控制代理 ✓、任务管理 ✓、制样机控制 ✓
- WebSocket实时通讯 ✓

**2. Placeholder scan:** 页面描述是概要性的，但足够subagent实现。

**3. Type consistency:** API模块使用shared包定义的请求体格式，与后端接口一致 ✓
