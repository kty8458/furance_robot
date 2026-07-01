#!/usr/bin/env python3
"""Modbus 双夹爪控制节点 — Service 接口版本。

从 grippers_control 包移植: action → service, 兼容单夹爪场景
(任一从站连接失败不影响节点启动, 仅记录 warning)。

Service: /gripper_control (control_interfaces/srv/GripperControl)
Request:
  string arm            # left / right
  string method         # open / close / position
  float64 torque        # 0-100
  float64 position      # 0-100
Response:
  bool success
  string gripper_status
  string gripper_message
  float64 current_position
"""

import logging
import time
from threading import Lock

import rclpy
from rclpy.node import Node
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor

logger = logging.getLogger("modbus_gripper")
_lh = logging.getLogger("modbus_gripper")
if not _lh.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("[%(name)s %(levelname)s] %(message)s"))
    _lh.addHandler(_h)
    _lh.setLevel(logging.INFO)
    _lh.propagate = False


SERIAL_PORT = "/dev/ttyUSB0"
BAUDRATE = 115200
DEVICE_ID_LEFT = 1
DEVICE_ID_RIGHT = 2


class ModbusGripperNode(Node):
    def __init__(self):
        super().__init__("modbus_gripper")
        self.get_logger().info("ModbusGripperNode starting...")

        # ---- 串口连接 ----
        try:
            from pymodbus.client import ModbusSerialClient
        except ImportError:
            self.get_logger().fatal(
                "pymodbus 未安装. 请 pip install 'pymodbus>=3.0'"
            )
            raise

        self._client = ModbusSerialClient(
            port=SERIAL_PORT, baudrate=BAUDRATE, timeout=1,
            parity="N", stopbits=1, bytesize=8,
        )

        # 尝试连接, 失败也继续启动 (允许单夹爪/无夹爪场景下节点可用)
        retry = 0
        while not self._client.connect() and retry < 5:
            self.get_logger().warning(
                f"Modbus 串口未就绪 ({SERIAL_PORT}), 重试中 ({retry + 1}/5)..."
            )
            time.sleep(0.5)
            retry += 1
        if not self._client.connected:
            self.get_logger().warning(
                f"Modbus 串口 {SERIAL_PORT} 未连接, 节点继续启动但所有请求将失败"
            )

        self._io_lock = Lock()  # 串口共享, 串行访问

        # ---- 探测左右夹爪是否存在 ----
        self.left_present, self.left_map_max = self._probe_device(DEVICE_ID_LEFT, "left")
        self.right_present, self.right_map_max = self._probe_device(DEVICE_ID_RIGHT, "right")

        if not self.left_present and not self.right_present:
            self.get_logger().warning("两个夹爪都未探测到, 节点仍启动但无可用从站")

        # ---- Service 服务器 ----
        from control_interfaces.srv import GripperControl
        cb_group = ReentrantCallbackGroup()
        self._srv = self.create_service(
            GripperControl,
            "/gripper_control",
            self._handle_request,
            callback_group=cb_group,
        )
        self.get_logger().info(
            f"Service /gripper_control ready (left={'OK' if self.left_present else 'MISSING'}, "
            f"right={'OK' if self.right_present else 'MISSING'})"
        )

    # ----- 探测 -----

    def _probe_device(self, device_id: int, label: str) -> tuple[bool, int]:
        """探测从站是否存在, 同时读取 map_max。返回 (present, map_max)."""
        # 每次探测前确保串口连接 (pymodbus 对无响应 slave 会断开连接)
        if not self._client.connected:
            self.get_logger().info(f"串口断开, 重新连接后探测 {label} 夹爪 (device_id={device_id})...")
            try:
                self._client.connect()
            except Exception as e:
                self.get_logger().warning(f"{label} 夹爪 (device_id={device_id}) 串口重连失败: {e}")
                return False, 0
            if not self._client.connected:
                self.get_logger().warning(f"{label} 夹爪 (device_id={device_id}) 串口仍未连接, 跳过")
                return False, 0
        self.get_logger().info(f"开始探测 {label} 夹爪 (device_id={device_id})...")
        high = self._read_register(0x0406, count=1, device_id=device_id)
        low = self._read_register(0x0407, count=1, device_id=device_id)
        if high is None or low is None:
            self.get_logger().warning(
                f"{label} 夹爪 (device_id={device_id}) 未响应, 跳过"
            )
            return False, 0
        map_max = (high[0] << 16) + low[0]
        self.get_logger().info(
            f"{label} 夹爪 (device_id={device_id}) 在线, map_max={map_max}"
        )
        return True, map_max

    # ----- Modbus 读写 (带锁) -----

    def _ensure_connected(self) -> bool:
        """确保串口已连接, 断开则重连。"""
        if self._client.connected:
            return True
        return self._try_reconnect()

    def _try_reconnect(self) -> bool:
        """尝试重新连接串口。先关闭旧连接再重连。"""
        with self._io_lock:
            try:
                if self._client.connected:
                    self._client.close()
            except Exception:
                pass
            try:
                ok = self._client.connect()
                if ok:
                    self.get_logger().info("串口重连成功")
                return bool(ok)
            except Exception as e:
                self.get_logger().error(f"串口重连失败: {e}")
                return False

    def _write_register(self, address: int, value: int, device_id: int) -> bool:
        if not self._ensure_connected():
            return False
        with self._io_lock:
            try:
                result = self._client.write_register(address, value, slave=device_id)
                if hasattr(result, "isError") and result.isError():
                    self.get_logger().error(
                        f"写入寄存器 {hex(address)} (device_id={device_id}) 错误: {result}"
                    )
                    return False
                return True
            except Exception as e:
                self.get_logger().error(
                    f"写入寄存器 {hex(address)} (device_id={device_id}) 异常: {e}"
                )
                self._try_reconnect()
                return False

    def _read_register(self, address: int, count: int = 1, device_id: int = 1):
        if not self._ensure_connected():
            return None
        with self._io_lock:
            try:
                result = self._client.read_holding_registers(
                    address=address, count=count, slave=device_id
                )
                if result is None or (hasattr(result, "isError") and result.isError()):
                    return None
                return result.registers
            except Exception as e:
                self.get_logger().error(
                    f"读取寄存器 {hex(address)} (device_id={device_id}) 异常: {e}"
                )
                # 异常后尝试重连, 供下次使用
                self._try_reconnect()
                return None

    # ----- 动作 -----

    def _open_hand(self, device_id: int, torque: float) -> bool:
        ok = (
            self._write_register(0x0102, 0, device_id)
            and (time.sleep(0.05) or True)
            and self._write_register(0x0103, 10, device_id)
            and (time.sleep(0.05) or True)
            and self._write_register(0x0105, int(torque), device_id)
            and (time.sleep(0.05) or True)
            and self._write_register(0x0108, 1, device_id)
        )
        return ok

    def _close_hand(self, device_id: int, torque: float) -> bool:
        ok = (
            self._write_register(0x0102, 1, device_id)
            and (time.sleep(0.05) or True)
            and self._write_register(0x0103, 10, device_id)
            and (time.sleep(0.05) or True)
            and self._write_register(0x0105, int(torque), device_id)
            and (time.sleep(0.05) or True)
            and self._write_register(0x0108, 1, device_id)
        )
        return ok

    def _position_control(self, device_id: int, torque: float, position: float, max_map: int) -> bool:
        position_write = int((position / 100.0) * max_map) if max_map else int(position)
        ok = (
            self._write_register(0x0102, 0, device_id)
            and (time.sleep(0.05) or True)
            and self._write_register(0x0103, position_write, device_id)
            and (time.sleep(0.05) or True)
            and self._write_register(0x0105, int(torque), device_id)
            and (time.sleep(0.05) or True)
            and self._write_register(0x0108, 1, device_id)
        )
        return ok

    def _wait_arrival(self, device_id: int, method: str, timeout: float = 3.0) -> tuple[bool, int]:
        """轮询到达信号, 返回 (arrived, current_position)."""
        start = time.time()
        cur_pos = 0
        while time.time() - start < timeout:
            if method == "close":
                t_regs = self._read_register(0x0601, count=1, device_id=device_id)
                p_regs = self._read_register(0x0602, count=1, device_id=device_id)
                if t_regs is None or p_regs is None:
                    time.sleep(0.1); continue
                arrived = (t_regs[0] == 1) or (p_regs[0] == 1)
            else:
                a_regs = self._read_register(0x0602, count=1, device_id=device_id)
                if a_regs is None:
                    time.sleep(0.1); continue
                arrived = (a_regs[0] == 1)

            high = self._read_register(0x060D, count=1, device_id=device_id)
            low = self._read_register(0x060E, count=1, device_id=device_id)
            if high is not None and low is not None:
                cur_pos = (high[0] << 16) + low[0]

            if arrived:
                return True, cur_pos
            time.sleep(0.1)
        return False, cur_pos

    # ----- Service callback -----

    def _handle_request(self, request, response):
        arm = request.arm
        method = request.method
        torque = float(request.torque)
        position = float(request.position)

        self.get_logger().info(
            f"请求: arm={arm} method={method} torque={torque:.1f} position={position:.1f}"
        )

        if arm == "left":
            present = self.left_present
            device_id = DEVICE_ID_LEFT
            map_max = self.left_map_max
        elif arm == "right":
            present = self.right_present
            device_id = DEVICE_ID_RIGHT
            map_max = self.right_map_max
        else:
            response.success = False
            response.gripper_status = "失败"
            response.gripper_message = f"未知 arm: {arm}"
            return response

        # 每次请求前确保串口连接 (pymodbus 超时后会断开)
        if not self._ensure_connected():
            response.success = False
            response.gripper_status = "失败"
            response.gripper_message = "串口未连接"
            return response

        if not present:
            response.success = False
            response.gripper_status = "未连接"
            response.gripper_message = f"{arm} 夹爪未连接 (device_id={device_id})"
            return response

        if method == "open":
            ok = self._open_hand(device_id, torque)
            action_label = "打开"
        elif method == "close":
            ok = self._close_hand(device_id, torque)
            action_label = "关闭"
        elif method == "position":
            ok = self._position_control(device_id, torque, position, map_max)
            action_label = "位置控制"
        else:
            response.success = False
            response.gripper_status = "失败"
            response.gripper_message = f"未知 method: {method}"
            return response

        if not ok:
            response.success = False
            response.gripper_status = "失败"
            response.gripper_message = f"{action_label}指令下发失败"
            return response

        arrived, cur_pos = self._wait_arrival(device_id, method)
        response.current_position = float(cur_pos)
        if arrived:
            response.success = True
            response.gripper_status = "成功"
            response.gripper_message = f"{action_label}完成"
        else:
            response.success = False
            response.gripper_status = "超时"
            response.gripper_message = f"{action_label} 3s 内未到达"
        return response

    def destroy_node(self):
        try:
            self._client.close()
        except Exception:
            pass
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = ModbusGripperNode()
    executor = MultiThreadedExecutor()
    try:
        rclpy.spin(node, executor=executor)
    except KeyboardInterrupt:
        node.get_logger().info("节点已停止")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
