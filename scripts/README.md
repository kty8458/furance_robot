# Robot Control 自启动脚本

本目录包含 3 个 systemd 服务，开机自动启动控制系统三个组件。

**跨机部署友好**：所有路径、用户名都是占位符（`__USER__`/`__USER_HOME__`/`__PROJECT_ROOT__`），安装时根据当前用户和项目实际位置自动替换。

## 服务清单

| 服务 | 单元名 | 端口 | 依赖 |
|------|--------|------|------|
| ROS2 节点管理器 | `furance-node-manager.service` | — | `network-online.target` |
| 后端 (FastAPI) | `furance-backend.service` | 8000 | `furance-node-manager.service` |
| 前端 (vite preview) | `furance-frontend.service` | 5173 | — |

## 一次性安装

在任意机器上把项目克隆到任意位置后：

```bash
cd <project>/scripts
./install_autostart.sh
```

脚本会：
1. 编译前端生产包 (`npm install` + `npm run build`)
2. 用 `sed` 把模板中的占位符替换为当前用户/路径
3. 渲染后的 wrapper 写入 `/usr/local/bin/`
4. 渲染后的 `.service` 写入 `/etc/systemd/system/`
5. `systemctl daemon-reload` + `enable` + `start`

## 占位符替换规则

| 占位符 | 替换为 | 示例 |
|--------|--------|------|
| `__USER__` | `$(id -un)` | `kty` |
| `__USER_HOME__` | `$HOME` | `/home/kty` |
| `__PROJECT_ROOT__` | 安装脚本所在目录的父目录 | `/home/kty/Desktop/furance_robot` |

## 状态查看

```bash
systemctl status furance-node-manager
systemctl status furance-backend
systemctl status furance-frontend
```

## 日志查看

```bash
journalctl -u furance-node-manager -f
journalctl -u furance-backend -f
journalctl -u furance-frontend -f
```

## 卸载

```bash
sudo systemctl disable --now furance-node-manager furance-backend furance-frontend
sudo rm /etc/systemd/system/furance-*.service
sudo rm /usr/local/bin/furance-*.sh
sudo systemctl daemon-reload
```

## 重新安装（项目移动后）

如果项目目录变了或换了机器，重新跑 `./install_autostart.sh` 会用新路径覆盖旧文件。

## 手动控制（不通过开机自启）

```bash
sudo systemctl start furance-node-manager
sudo systemctl stop furance-frontend
sudo systemctl restart furance-backend
```
