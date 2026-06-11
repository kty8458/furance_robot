# 相机系统重构 — 设计文档

**日期**: 2026-06-11
**状态**: 已批准

## 概述

将相机系统从基于 ROS2 topic 订阅的间接模式重构为基于 pyorbbecsdk 直连的模式，支持多相机管理、WebSocket 视频推流、配置化相机位置绑定，并为后续视觉算法开发提供同步数据获取 API。

## 动机

1. 当前 `RealCameraClient` 通过订阅 ROS2 topic (`/camera_X/color/image_raw`) 获取图像帧，依赖 `orbbec_camera_node` 先启动相机
2. 相机 ID 硬编码为 `camera_1/2/3`，无法灵活绑定物理相机到逻辑位置
3. 前端通过 HTTP 轮询 `/camera/frame` 获取 JPEG，延迟高、效率低
4. 视频类型仅支持 raw/grayscale，不支持深度图渲染
5. 视觉算法开发缺少直接的帧数据获取方法

## 架构

```
ros2_ws/src/t1_robot/python_pkgs/python_pkgs/vision/
├── camera_config.yaml           # 相机→位置绑定配置
├── camera_manager.py            # ROS2 Node: 多相机生命周期管理 + 同步帧API
├── camera_ws_handler.py         # WebSocket 推流处理器 (被 robot_control mount)
└── orbbec_camera_example.py     # (已存在) 独立示例脚本

robot_control/backend/app/
├── main.py                      # + mount camera_ws_handler 的 WS router
├── api/camera.py                # 改造: list/stream 接口调 ROS2 Service
└── ros2/camera_client.py        # 改造: 新增 ROS2 Service 客户端方法

robot_control/frontend/src/
├── views/CameraView.vue         # 改造: WS 推流 + 动态相机列表 + 视频类型
├── views/WorkflowEditor.vue     # 改造: 视觉步骤相机选择动态获取
└── api/camera.js                # 改造: 新增 list 接口, 移除 getFrame
```

## 数据流

```
前端 CameraView.vue
  │
  │ ① HTTP GET  /api/v1/robot/{id}/camera/list
  │    → robot_control → ROS2 Service /camera/list → camera_manager
  │    ← 返回相机列表 [{id, name, position, ...}]
  │
  │ ② WebSocket  ws://<host>/ws/v1/camera  (同端口, 无跨域)
  │    前端 → {"action":"subscribe","camera_id":"head","stream_type":"raw"}
  │    前端 ← {"type":"frame","camera_id":"head","stream_type":"raw","data":"<base64>"}
  │    前端 ← ...持续推送...
  │    前端 → {"action":"unsubscribe"}
  │
  ▼
<img> 实时渲染 base64 JPEG 帧
```

## 组件设计

### 1. camera_config.yaml

相机到逻辑位置的绑定配置，通过 serial 或 usb_port 匹配物理设备。

```yaml
cameras:
  - id: "head"
    name: "头部相机"
    serial: "CP0E163000FP"
    usb_port: "2-1"
    position: "head"
    color_stream: { width: 1280, height: 720, fps: 30 }
    depth_stream: { width: 848, height: 480, fps: 30 }

  - id: "left_arm"
    name: "左臂相机"
    usb_port: "2-2"
    position: "left_arm"

  - id: "right_arm"
    name: "右臂相机"
    usb_port: "2-3"
    position: "right_arm"
```

- `id`: 逻辑 ID，前端使用
- `serial` / `usb_port`: 物理匹配方式，serial 优先
- `position`: 安装位置标签
- `color_stream` / `depth_stream`: 可选，覆盖默认流配置

### 2. camera_manager.py

核心相机管理器，作为 ROS2 Node 运行。

**职责**:
- 启动时读取 `camera_config.yaml`，按 serial/usb_port 匹配物理设备
- 为每个相机创建 `pyorbbecsdk.Pipeline` 实例
- 管理采集线程：持续拉取帧，缓存最新一帧
- 暴露 ROS2 Service 供 robot_control 调用
- 暴露同步 Python API 供视觉算法开发

**ROS2 Services**:

| Service | 请求 | 响应 |
|---------|------|------|
| `/camera/list` | `{}` | `{cameras: [{id, name, position, serial, color_profiles, depth_profiles, connected}]}` |
| `/camera/stream/start` | `{camera_id, stream_type}` | `{success, message}` |
| `/camera/stream/stop` | `{camera_id}` | `{success, message}` |

**同步 Python API** (供算法开发):

```python
from python_pkgs.vision.camera_manager import CameraManager

manager = CameraManager()
rgb = manager.get_latest_color("head")           # np.ndarray (H, W, 3) BGR
depth = manager.get_latest_depth("head")         # np.ndarray (H, W) float32 mm
rgb, depth = manager.get_aligned_frames("head")  # 对齐的 RGB-D
```

**帧缓存**:
- 每个相机维护 `_latest_color_frame` 和 `_latest_depth_frame`
- 采集线程以相机配置的帧率持续拉取
- `get_latest_*()` 返回最新帧的拷贝（线程安全）

**依赖**:
- pyorbbecsdk (pip 包, 需 LD_LIBRARY_PATH 指向 site-packages/pyorbbecsdk)
- rclpy
- numpy, opencv-python

### 3. camera_ws_handler.py

WebSocket 推流处理器，被 robot_control FastAPI 挂载到 `/ws/v1/camera`。

**与 camera_manager 的通信**:

`camera_ws_handler` 和 `camera_manager` 运行在同一进程内（robot_control 进程）。
robot_control 在 real 模式下已启动 rclpy（通过 `Ros2Runtime`），`camera_manager` 作为该进程内的 ROS2 Node 实例化，其帧采集在后台线程运行。

`camera_ws_handler` 直接调用 `camera_manager` 的同步 getter 方法获取帧数据：
```python
from python_pkgs.vision.camera_manager import camera_manager  # 全局单例

rgb = camera_manager.get_latest_color("head")
depth = camera_manager.get_latest_depth("head")
```

这样帧获取零 IPC 开销，适合高频推送场景。

**职责**:
- 接收前端的 subscribe/unsubscribe 消息
- 从 `camera_manager` 获取最新帧，编码为 JPEG base64
- 按相机帧率推送帧数据
- 支持连接断开时自动清理订阅

**协议**:

```json
// 前端 → 服务端: 订阅
{"action": "subscribe", "camera_id": "head", "stream_type": "raw"}

// 前端 → 服务端: 取消订阅
{"action": "unsubscribe"}

// 服务端 → 前端: 视频帧推送
{"type": "frame", "camera_id": "head", "stream_type": "raw", "data": "base64_encoded_jpeg"}

// 服务端 → 前端: 错误
{"type": "error", "message": "Camera not found: xxx"}
```

**stream_type 支持**:
- `raw`: 原始彩色图像
- `depth`: 深度图 (3D 浮雕渲染)
- `annotated`: 带识别框标注 (预留, 后续开发)

**帧率控制**:
- 按相机配置的 FPS 推送，避免前端积压
- 如果帧尚未更新，跳过推送（不等帧）

**挂载方式**:
- `camera_ws_handler.py` 导出一个 FastAPI `APIRouter`
- `robot_control/backend/app/main.py` 中 `app.include_router(camera_ws_router)`
- 复用 robot_control 的端口和 CORS 配置

### 4. robot_control 后端改动

**app/api/camera.py**:

| 接口 | 改动 |
|------|------|
| `GET /camera/list` | 新增: 调 ROS2 Service `/camera/list`, 返回相机列表 |
| `POST /camera/publish/start` | 删除: 不再需要启动 orbbec_camera_node |
| `POST /camera/publish/stop` | 删除 |
| `POST /camera/stream/start` | 改造: 调 ROS2 Service `/camera/stream/start` |
| `POST /camera/stream/stop` | 改造: 调 ROS2 Service `/camera/stream/stop` |
| `GET /camera/frame` | 删除: 改为 WebSocket 推流 |
| `POST /camera/detect` | 保留: 视觉检测接口不变 |

**app/ros2/camera_client.py**:

- 新增方法: `get_camera_list()` → 调 `/camera/list` Service
- 改造 `start_stream()` / `stop_stream()` → 调对应 ROS2 Service
- 删除 `_subs` 订阅管理逻辑（不再直接订阅 ROS2 topic）
- 保留 `detect_grasp_pose()` 不变
- MockCameraClient 同步更新

**app/main.py**:

```python
# 新增
from python_pkgs.vision.camera_ws_handler import router as camera_ws_router
app.include_router(camera_ws_router)
```

### 5. 前端改动

**CameraView.vue**:

| 改动项 | 说明 |
|--------|------|
| 相机列表 | 从 `GET /camera/list` 动态获取，不再硬编码 |
| 视频类型 | `raw` (原始画面) / `depth` (深度图) / `annotated` (识别画面, 预留) |
| 连接按钮 | 建立 WebSocket → `ws://<host>/ws/v1/camera`, 发送 subscribe |
| 断开按钮 | 发送 unsubscribe + 关闭 WebSocket |
| 视频渲染 | 收到 frame 消息后设置 `<img :src="'data:image/jpeg;base64,' + frameData">` |
| 移除 | HTTP 轮询逻辑 (`setInterval` + `getFrame`) |

**WorkflowEditor.vue**:

| 改动项 | 说明 |
|--------|------|
| 视觉步骤相机选择 | 从 `GET /camera/list` 动态获取选项，不再硬编码 camera_1/2/3 |

**api/camera.js**:

```javascript
export const cameraApi = {
  list: () => api.get(`/robot/${ROBOT_ID}/camera/list`),
  startStream: (cameraId, streamType) => api.post(`/robot/${ROBOT_ID}/camera/stream/start`, { camera_id: cameraId, stream_type: streamType }),
  stopStream: (cameraId) => api.post(`/robot/${ROBOT_ID}/camera/stream/stop`, { camera_id: cameraId }),
  detect: (cameraId, scene) => api.post(`/robot/${ROBOT_ID}/camera/detect`, { camera_id: cameraId, scene }),
  // getFrame 移除 — 改为 WebSocket 推流
}
```

### 6. 跨域处理

- `camera_ws_handler` 挂载到 robot_control FastAPI，复用同一端口
- 前端 WebSocket 连接 `ws://<当前页面host>/ws/v1/camera`，无跨域问题
- 局域网访问时同样无跨域问题（浏览器视为同源）

## LD_LIBRARY_PATH 处理

`pyorbbecsdk` pip 包自带 `libOrbbecSDK.so.2` (v2.8.6)，与 ROS2 自带的 v2.7.6 冲突。

**解决方案**:
- `camera_manager.py` 中 import pyorbbecsdk 前，检查并修正 `LD_LIBRARY_PATH`
- 若 site-packages/pyorbbecsdk 不在路径中，用 `os.execve` 重启自身
- 与 `orbbec_camera_example.py` 已有的处理方式一致

## 错误处理

| 场景 | 处理 |
|------|------|
| 配置的相机未连接 | `/camera/list` 返回 `connected: false`，前端灰显 |
| 订阅不存在的相机 | WS 返回 `{type: "error", message: "Camera not found"}` |
| Pipeline 启动失败 | ROS2 Service 返回 `{success: false, message: "..."}` |
| WebSocket 连接断开 | 前端自动清理，服务端移除订阅 |

## 实现顺序

1. `camera_config.yaml` — 配置文件
2. `camera_manager.py` — 核心管理器 (ROS2 Node + 同步 API)
3. `camera_ws_handler.py` — WebSocket 推流处理器
4. `robot_control/backend/app/ros2/camera_client.py` — 改造
5. `robot_control/backend/app/api/camera.py` — 改造
6. `robot_control/backend/app/main.py` — mount WS router
7. `robot_control/frontend/src/api/camera.js` — 改造
8. `robot_control/frontend/src/views/CameraView.vue` — 改造
9. `robot_control/frontend/src/views/WorkflowEditor.vue` — 改造
