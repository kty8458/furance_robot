# 工作流与示教点优化计划

## 目标
1. 示教点分全局/工作流两级存储
2. 页面切换保留状态 (keep-alive)
3. 从中间步骤执行工作流
4. 循环执行工作流

## 改动清单

### 1. 示教点分级存储 (后端 + 前端)

**后端 `arm_service.py` + `api/arm.py`:**
- `list_teach(robot_id, workflow_name=None)`:
  - `workflow_name=None` -> 读 `presets.json` (全局)
  - `workflow_name="xxx"` -> 合并全局 + `workflows/<robot>/<name>/teach_presets.json`
- `save_teach(robot_id, preset, workflow_name=None)`:
  - `workflow_name=None` -> 存全局 `presets.json`
  - 否则存到 `workflows/<robot>/<name>/teach_presets.json`
- `delete_teach` / `exec_teach` / `compose_teach` 同理加 `workflow_name` 参数
- API 端点加 `?workflow=<name>` query 参数

**前端:**
- `armApi.teachList(workflow?)` / `teachSave(arm, name, method, workflow?)` 等
- `ArmControl.vue`: 无选中工作流时操作全局, 选中工作流时操作工作流级
- `WorkflowEditor.vue`: 选中工作流后 `loadTeachPresets(workflowName)`

### 2. 前端状态保留 (keep-alive)

**`App.vue`:**
```html
<router-view v-slot="{ Component }">
  <keep-alive :include="['WorkflowEditor', 'ArmControl']">
    <component :is="Component" />
  </keep-alive>
</router-view>
```
- `WorkflowEditor.vue` 和 `ArmControl.vue` 的 `name` 属性需匹配 keep-alive include
- 切换页面不重新加载, 回来时保留 currentWorkflow / teachList 等

**数据新鲜度:**
- `onActivated` 钩子里做轻量刷新 (只拉列表标题, 不拉完整数据)
- 用户手动点「刷新」按钮才拉完整数据

### 3. 从中间步骤执行 (后端)

**`WorkflowExecuteRequest` 新增:**
```python
start_step_index: int = 0  # 从第几步开始执行 (0-based)
```

**`_run_workflow` 改动:**
- `for i, step in enumerate(workflow.steps)` -> `for i, step in enumerate(workflow.steps[start:], start=start)`
- **视觉依赖处理**: 跳过的视觉步骤如果被后续引用, 从 context 中查不到 -> 报错提示用户
- 手动模式兼容: start_step_index 之后正常执行

**前端:**
- 执行弹窗新增「从第 N 步开始」输入框
- 步骤列表显示序号, 方便用户选择起始步骤

### 4. 循环执行 (后端)

**`WorkflowExecuteRequest` 新增:**
```python
loop: bool = False          # 是否循环执行
loop_interval: float = 0.0   # 循环间隔 (秒)
```

**`_run_workflow` 改动:**
```python
while True:
    # 执行完整工作流
    for i, step in enumerate(...):
        ...
    if not loop or cancel_event.is_set():
        break
    if loop_interval > 0:
        await asyncio.sleep(loop_interval)
```
- 循环模式下失败不中断, 记录失败步骤后继续下一轮
- 取消时退出循环

**前端:**
- 执行弹窗新增「循环执行」勾选 + 间隔输入

## 实施顺序

1. **后端** `shared/models/workflow.py` + `workflow_service.py` + `arm_service.py` + `api/arm.py` + `api/workflow.py`
2. **前端 API** `arm.js` + `workflow.js`
3. **前端 UI** `App.vue` (keep-alive) + `WorkflowEditor.vue` + `ArmControl.vue`
