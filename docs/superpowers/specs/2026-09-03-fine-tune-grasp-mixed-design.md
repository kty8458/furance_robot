# 取样杆闭环微调抓取集成工作流混合控制 — 设计文档

日期：2026-09-03
状态：已确认（方案 A）

## 背景与目标

`orbbec_vision/test_fine_tune_grasp.py` 已在真机验证了基于 YOLO 分割 + 深度的取样杆闭环微调功能：
三阶段闭环（roll 对齐 → y 对齐 → 深度进给），通过 TF 查询 EE 位姿、tool 系增量换算后调
`/move_pose`（MoveP）运动。

该脚本是独立测试脚本，**直连相机**（pyorbbecsdk Pipeline 独占设备），与实际控制系统的
相机管理节点（camera_manager，唯一持有相机的进程）冲突。目标：把该功能集成进工作流的
`mixed`（混合控制）步骤，闭环测量经由相机管理节点完成，不再直连相机。

### 已确认的边界决策

- **功能边界**：仅微调段。前提是臂已通过 QR 标定/vision 步骤到达预抓取位；闭爪仍由后续
  `gripper` 步骤完成。与测试脚本一致。
- **ref_depth 存储**：工作流 mixed 步骤参数（params），与预抓取位姿绑定，每个步骤可不同。
- **方案**：A — 测量下沉相机节点（新增 measure 服务）+ 闭环编排留在 mixed 功能。
  （否决 B：闭环整体下沉相机侧服务，相机节点做运动控制职责混乱且无法用 ctx 取消/报进度；
  否决 C：mixed 功能 subprocess 跑现有脚本，直连相机与 camera_manager USB 独占冲突。）

## 总体架构与数据流

```
工作流 mixed 步骤 (function="fine_tune_grasp", params={camera, arm, ref_depth, ...})
    │ /mixed/execute (GenericCommand)
    ▼
mixed_executor 节点 ── functions/fine_tune_grasp.py (三阶段闭环编排)
    │                                      │
    │ ctx.ros_call                         │ ctx.ros_call_typed (MoveP)
    │ /camera/fine_tune_measure            │ /move_pose
    ▼                                      │
camera_manager 节点                        │
  对齐取帧 → YOLO → 测量算法                ▼
  返回 {roll_err, dy_mm, depth_med,      TF base_link→EE
        fine_tune偏移/符号, viz路径}      (mixed_executor 节点内新增 listener)
```

闭环模式：**测量（问相机）→ 算增量（纯数学）→ 运动（问手臂）→ 等停稳（问 TF）→ 循环**。
每次迭代边界检查 `ctx.check_cancel()`，每阶段用 `ctx.set_progress()` 上报。

## orbbec_vision 侧改动

### 1. 新库模块 `fine_tune_measure.py`

从测试脚本迁移纯算法（无 ROS 依赖）：

- `mask_axis()`：mask 像素 PCA 求杆中轴线
- `measure()`：从一帧计算观测量（roll_err_deg / dy_px / dy_mm / depth_med）
- `draw_viz()`：可视化叠加图
- 算法常量：`DEPTH_SAMPLES`、`DEPTH_SAMPLE_WIN`、`MIN_DEPTH_SAMPLES`、
  `MAX_ROLL_ERR_DEG` 等
- `load_fine_tune_cfg()`：读 camera_config.yaml 中该相机的 fine_tune 偏移/符号配置

`test_fine_tune_grasp.py` 改为从本模块 import——单一算法实现，脚本保留用于真机调试
（dry-run 等能力不废）。

### 2. `camera_manager_node.py` 新增 `/camera/fine_tune_measure` 服务

GenericCommand 服务，与现有 `/camera/compute_pose` 同构。

**入参**：`{camera_id, settle_frames, settle_sec, save_viz}`

**处理流程**（仿照 calibrate/compute_pose 的"按需启流"模式）：

1. 记录该相机当前流状态（是否在流、stream_type）
2. 若在流则停止，用 color + depth + `FULL_FRAME_REQUIRE` 配置重启 pipeline
3. `AlignFilter`（depth→color）对齐循环取帧，settle 逻辑与脚本一致：丢 N 帧 +
   时长条件（保证取到调用时刻之后的新画面——闭环中臂刚停稳，管线里的旧帧会污染测量）
4. 复用节点内已有的 `_yolo_detectors[camera_id]` 做 YOLO 分割（配置来自
   `yolo_config.yaml`，无需传模型路径）
5. 调 `measure()` 计算，保存可视化图到 `data/fine_tune/<时间戳>/`
6. `finally` 恢复原流状态

**返回**：

```json
{
  "success": true,
  "roll_err_deg": ..., "dy_px": ..., "dy_mm": ..., "depth_med": ...,
  "conf": ..., "mask_area_px": ..., "viz_path": "...",
  "fine_tune": {"cam_y_offset_mm": ..., "depth_offset_mm": ...,
                "roll_sign": ..., "y_sign": ..., "z_sign": ...}
}
```

偏移/符号由相机节点从 camera_config.yaml 读出一并返回——mixed 功能不解析 yaml，
单一配置来源。

**互斥**：per-camera 锁。测量服务执行期间该相机的推流/标定等其他请求排队等待，
防止抢 pipeline。

## mixed_execution 侧改动

### 框架扩展（两处小改动，通用能力）

1. **`RosCaller` 支持类型化服务**：新增
   `call_typed(service_name, srv_type, request, timeout)`，复用现有
   "client 缓存 + call_async + 轮询 future" 模式，返回原生 response 对象。
   用于 `/move_pose`（`control_interfaces/srv/MoveP`）。
   `setup.py`/`package.xml` 增加 `control_interfaces` 依赖。
2. **节点加 TF 能力**：`mixed_executor` 节点初始化时创建 `tf2_ros.Buffer` +
   `TransformListener`（主线程 spin 处理回调，工作线程带超时查询，与测试脚本
   ArmInterface 同模式）。

`ExecutionContext` 新增：

- `ctx.tf_lookup(parent, child, timeout)` → 4x4 numpy 矩阵或 None
- `ctx.ros_call_typed(service_name, srv_type, request, timeout)` → 原生 response

### `functions/fine_tune_grasp.py`（闭环编排）

```python
@mixed_function(
    name="fine_tune_grasp",
    description="取样杆三阶段闭环微调 (roll对齐→y对齐→深度进给), 前提: 臂已在预抓取位",
    params_schema={
        "camera":    {"type": "string", "default": "right_arm"},
        "arm":       {"type": "string", "default": "right"},   # left/right
        "ref_depth": {"type": "number", "required": True},     # 参考深度(米), 手动标定
        "max_iter":  {"type": "int", "default": 3},
        "roll_tol":  {"type": "number", "default": 1.0},       # 度
        "y_tol":     {"type": "number", "default": 2.0},       # mm
        "depth_tol": {"type": "number", "default": 0.030},     # 米
        "dry_run":   {"type": "bool", "default": False},
    },
    moves_base=False,
)
```

执行逻辑 = 测试脚本 `main()` 的迁移，基础设施替换：

| 脚本中的设施 | 集成后 |
|---|---|
| `CameraGrabber.grab()` + YOLO + `measure()` | `ctx.ros_call("/camera/fine_tune_measure", ...)` 一次完成 |
| `load_fine_tune_cfg()` 读 yaml | 用测量服务返回的 `fine_tune` 字段 |
| `ArmInterface.get_T_base_ee()` | `ctx.tf_lookup("base_link", ee_link)` |
| `ArmInterface.move_p()` | `ctx.ros_call_typed("/move_pose", MoveP, req)` |
| `ArmInterface.wait_stationary()` | TF 轮询 + `ctx.check_cancel()` |
| `print` 进度 | `ctx.set_progress(pct, "阶段2 y迭代2: dy=+3.1mm")` |

三阶段控制流（与脚本一致）：

1. **阶段1 roll 对齐**：测量 → roll 超阈值则绕 tool x 旋转修正（限幅 max_roll_step），
   收敛或达 max_iter
2. **阶段2 y 对齐**：roll 转正后才测 y（避免倾斜时中线处 dy 被杠杆臂污染）；
   dy = 测量值 − cam_y_offset，超阈值沿 tool y 修正（限幅）；roll 漂移则先转正
3. **阶段3 深度进给**：一次执行。dz = (测量深度 − ref_depth)×1000 + depth_offset，
   超容差拒动；<1mm 跳过

位姿数学（`rpy_to_R`/`R_to_quat`/`T_from_tq`/`tool_offset_T`）随函数迁移——与
workflow_service 的 `_apply_pose_offset` 同源约定，保持本地副本符合现有惯例。

返回值：最终收敛状态（各阶段迭代次数、最终 roll/dy/dz、viz 路径列表），出现在
工作流步骤结果 data 中。

## 工作流侧

**引擎零改动**。`MixedStepConfig` 已支持任意 `function + params`，`/mixed/list`
自动发现新功能。

使用方式（在 `抓取测试.json` 的 QR 引导预抓取 `upper_limb` 步骤之后、闭爪
`gripper` 步骤之前插入）：

```json
{"type": "mixed", "config": {
    "function": "fine_tune_grasp",
    "params": {"camera": "right_arm", "arm": "right", "ref_depth": 0.35},
    "timeout": 300, "moves_base": false
}}
```

## 错误处理

### 相机侧（measure 服务，失败统一返回 `{success: false, message, stage}`）

| 失败模式 | 处理 |
|---|---|
| camera_id 未知 / 相机未连接 | 立即拒绝 |
| pipeline 启动失败 / 取帧超时（10s） | 拒绝，`finally` 恢复原流状态 |
| YOLO 未检测到 / mask 深度计算失败 | 拒绝，报"第 N 次迭代未检测到取样杆" |
| 杆轴与竖直夹角 > 30°（MAX_ROLL_ERR_DEG） | 视为误识别，拒绝（防 mask 抓错物体） |
| 服务执行期间该相机的其他请求 | per-camera 互斥锁，排队等待 |

### mixed 侧（功能状态机）

| 失败模式 | 处理 |
|---|---|
| 测量失败 | 功能失败，message 透传相机侧原因，工作流步骤 failed |
| `move_pose` 失败/超时 | 功能失败（臂位置未知，不继续） |
| 深度增量超容差 depth_tol | **拒动**，功能失败——安全设计，深度异常大概率是抓空/撞刀风险 |
| 等停稳超时 | 警告继续（与脚本一致） |
| 达到 max_iter 未完全收敛 | **警告但成功返回**，result 注明"未完全收敛"（与脚本一致；需要更严格可后续改为判失败） |
| 用户取消 | 每次迭代边界 + wait_stationary 轮询内 check_cancel()；单次 move_pose 原子不可中断，运动完成后立即生效（与 mixed 框架现有语义一致） |
| 工作流步骤超时（300s） | 最坏 ~7 次迭代 ×（测量 3-5s + 运动 + 停稳等待），余量充足 |

## 测试策略

1. **算法单元测试**（无 ROS/相机依赖，pytest）：`fine_tune_measure.py` 的
   `mask_axis`/`measure`——合成已知角度/位置的 mask + 合成深度图，断言
   roll_err/dy_mm/depth_med 数值精度；边缘情况（mask 太小、深度空洞、近水平杆轴）。
2. **闭环状态机测试**（mock ctx）：`fine_tune_grasp` 注入假 ctx——`ros_call`
   返回预置测量序列、`tf_lookup` 返回已知位姿、`ros_call_typed` 记录 move 请求。
   验证：正常收敛、roll 漂移回退、单步限幅、深度拒动、max_iter 警告、中途取消。
3. **真机分阶段验证**：`ros2 service call` 单独调 `/camera/fine_tune_measure`
   核对数值 → mixed 功能 dry_run（只测不动）→ 全闭环 → 完整工作流。

## 改动文件清单

| 包 | 文件 | 改动 |
|---|---|---|
| orbbec_vision | `fine_tune_measure.py`（新） | 测量算法库 |
| orbbec_vision | `tests/test_fine_tune_measure.py`（新） | 算法单元测试 |
| orbbec_vision | `camera_manager_node.py` | 新服务 handler + 对齐取帧 + per-camera 锁 |
| orbbec_vision | `test_fine_tune_grasp.py` | 改为 import 算法库（脚本保留用于调试） |
| mixed_execution | `mixed_executor_node.py` | RosCaller.call_typed + TF listener |
| mixed_execution | `executor.py` | ctx 新增 tf_lookup / ros_call_typed |
| mixed_execution | `functions/fine_tune_grasp.py`（新） | 闭环功能 |
| mixed_execution | `tests/test_fine_tune_grasp.py`（新） | mock ctx 状态机测试 |
| robot_control | `data/workflows/robot_001/抓取测试.json` | 插入 mixed 步骤示例 |

## 不做的事

- 不做 QR 定位 / 预抓取运动 / 闭爪（由现有 vision + upper_limb + gripper 步骤组合）
- 不改 mixed 步骤引擎与前端（现有 mixed 框架已支持）
- 不迁移 `/vision_detect` 占位符服务（另一项工作）
- 不做深度图/彩色图跨进程传输（测量在相机节点内完成，只传数字）
