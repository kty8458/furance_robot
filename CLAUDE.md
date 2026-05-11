# Furance Robot - 工程约束

## 项目概述
轮式双臂机器人控制系统和调度系统，Monorepo结构。

## 目录结构
- `shared/` - 共享Python包(furance-shared)，协议定义和数据模型
- `robot_control/` - 机器人控制系统(Ubuntu工控机)
- `dispatch/` - 调度系统(Win10控制柜)

## 开发规范

### Python
- Python 3.10+，使用type hints
- Linter: ruff (配置见 ruff.toml)
- 测试: pytest + pytest-asyncio
- 数据模型: Pydantic v2
- 异步: async/await，禁止同步阻塞调用

### 前端
- Vue 3 + Vite
- 功能性优先，工业风格

### 通讯协议
- HTTP: RESTful，统一响应格式 {code, message, data}
- WebSocket: JSON帧，类型字段区分(status/error/log)
- ROS2: Service模式，统一Request/Response
- 所有协议定义在 shared/src/furance_shared/protocol/

### 错误码
- 1xxx 通讯类
- 2xxx 硬件类
- 3xxx 业务类

### Git
- 提交格式: `<type>: <message>`
- type: feat/fix/chore/docs/refactor/test
- 每个功能点独立提交

## 关键设计决策
- 控制系统是硬件代理层，调度系统是业务逻辑层
- 手臂运控和示教仅暴露在控制系统API上
- 调度系统不直接与ROS2交互
- 示教数据存储在控制系统本地JSON文件
- L2接口预留抽象层，默认禁用

## 测试要求
- 共享包: 100%模型测试覆盖
- 后端: API集成测试 + Service单元测试
- 修改shared包后必须运行全量测试