# 系统管理页面 & 日志系统

## 变更清单

### 1. 页面重命名

- `/ros2` 路由路径不变
- 侧边栏标题：「ROS2节点」→「系统管理」
- `Ros2Nodes.vue` → 改为三卡片布局

### 2. 三卡片布局 (Ros2Nodes.vue)

| 卡片 | 功能 |
|---|---|
| ROS2节点管理 | 保持现有的节点列表、状态、启停、日志阅读不变 |
| 后台日志 | 按钮「查看最新200条日志」→ 读取 `control_system_backend-当天日期.log` 并显示 |
| 日志管理 | 日期选择器 + 来源下拉(后台/ROS2节点) → 查看历史日志 + 下载按钮 |

---

### 3. 文件日志系统 (后端)

**文件命名：** `data/logs/control_system_backend-YYYY-MM-DD.log`

**实现方式：** 在 `main.py` lifespan 启动时，往根 logger 添加 `TimedRotatingFileHandler`。所有 Python `logging.getLogger(__name__)` 的输出同时写入 stdout + 文件。

**日志格式：** `[2026-06-04 10:30:00] [INFO] [app.services.workflow_service] message`

### 4. 日志 API (新文件 `app/api/log_viewer.py`)

prefix: `/api/v1/system/logs`

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/backend` | 列出 `data/logs/` 下所有 `control_system_backend-YYYY-MM-DD.log`，按日期降序 |
| GET | `/backend/{date}` | 查看指定日期内容。参数 `?tail=200` 只取最后 N 行，不传则返回全部 |
| GET | `/backend/{date}/download` | 下载 `control_system_backend-{date}.log` |
| GET | `/ros2-nodes` | 扫描 `~/.ros/node_manager_logs/` 下的会话目录，返回可用的日期集合 |
| GET | `/ros2-nodes/{date}` | 查看那一天所有节点日志合并。参数 `?tail=200` |
| GET | `/ros2-nodes/{node}/{date}/download` | 下载单个节点某日的日志文件 |

### 5. 业务事件日志

在关键业务点加 `logger.info("EVENT key=value [...]")`：

| 文件 | 事件 |
|---|---|
| `workflow_service.py` | 执行开始/步骤完成/执行失败/取消 |
| `arm_service.py` | 机械臂移动调用 (method, arm, target) |
| `chassis_client.py` | 导航任务开始/完成/失败 |
| `chassis_poller.py` | 底盘状态数据异常 (连接丢失、响应超时) |

### 6. 日志保留

- 默认不清理
- 清理天数由 `log_retention_days: int = 0` 控制 (0=不清理)
- 启动时检查，若 >0 则删除早于 N 天的 `control_system_backend-*` 文件