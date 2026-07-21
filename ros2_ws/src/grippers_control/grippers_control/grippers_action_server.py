import rclpy
from rclpy.node import Node
from pymodbus.client import ModbusSerialClient
from rclpy.action import ActionServer
from control_interfaces.action import GripperAction  # 请根据实际包名和定义修改导入路径
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor

import time

class GripperActionServer(Node):
    def __init__(self):
        super().__init__('gripper_action_server')

        # 使用单一 Modbus 串口客户端（如果你有两个物理串口并且设备在不同端口，
        # 可把这里改为创建两个 client）
        self.client = ModbusSerialClient(
            port='/dev/ttyUSB0',   # 根据实际情况修改端口
            baudrate=115200,
            timeout=1,
            parity='N',
            stopbits=1,
            bytesize=8
        )

        while not self.client.connect():
            self.get_logger().error("无法连接到 Modbus 串口设备 (/dev/ttyUSB0)，重试中...")
            time.sleep(0.5)
        self.get_logger().info("成功连接到 Modbus 串口设备 (/dev/ttyUSB0)")

        # 设备 ID 映射：左手 device_id=1，右手 device_id=2
        self.device_id_left = 1
        self.device_id_right = 2

        # 读取左右夹具的最大映射值（分别通过 device_id 读取）
        left_map_high_regs = self.read_register(self.client, 0x0406, count=1, device_id=self.device_id_left)
        left_map_low_regs = self.read_register(self.client, 0x0407, count=1, device_id=self.device_id_left)
        if left_map_high_regs is None or left_map_low_regs is None:
            self.get_logger().error("读取左夹具 map_max 失败，设置为 0")
            self.left_map_max = 0
        else:
            left_map_max_high = left_map_high_regs[0]
            left_map_max_low = left_map_low_regs[0]
            self.left_map_max = (left_map_max_high << 16) + left_map_max_low
        self.get_logger().info(f"左夹具最大映射 (device_id={self.device_id_left})：{self.left_map_max}")

        right_map_high_regs = self.read_register(self.client, 0x0406, count=1, device_id=self.device_id_right)
        right_map_low_regs = self.read_register(self.client, 0x0407, count=1, device_id=self.device_id_right)
        if right_map_high_regs is None or right_map_low_regs is None:
            self.get_logger().error("读取右夹具 map_max 失败，设置为 0")
            self.right_map_max = 0
        else:
            right_map_max_high = right_map_high_regs[0]
            right_map_max_low = right_map_low_regs[0]
            self.right_map_max = (right_map_max_high << 16) + right_map_max_low
        self.get_logger().info(f"右夹具最大映射 (device_id={self.device_id_right})：{self.right_map_max}")

        # 创建 Action 服务器
        callback_group = ReentrantCallbackGroup()
        self._action_server = ActionServer(
            self,
            GripperAction,
            'gripper_action',
            execute_callback=self.execute_callback,
            callback_group=callback_group
        )

    def get_client(self, arm):
        """根据 arm 返回 (client, device_id, max_map)"""
        if arm == 'left':
            return self.client, self.device_id_left, self.left_map_max
        elif arm == 'right':
            return self.client, self.device_id_right, self.right_map_max
        else:
            self.get_logger().error(f"未知的臂标识: {arm}, 默认返回左夹具")
            return self.client, self.device_id_left, self.left_map_max

    def write_register(self, client, address, value, device_id=1):
        """
        写单个保持寄存器，使用 pymodbus 的 device_id 参数来指定从站地址
        """
        try:
            result = client.write_register(address, value, device_id=device_id)
            if hasattr(result, 'isError') and result.isError():
                self.get_logger().error(f"写入寄存器 {hex(address)} (device_id={device_id}) 时出现错误: {result}")
                return False
            return True
        except Exception as e:
            self.get_logger().error(f"写入寄存器 {hex(address)} (device_id={device_id}) 时出错: {e}")
            return False

    def read_register(self, client, address, count=1, device_id=1):
        """
        读取保持寄存器，返回 registers 列表或 None
        """
        try:
            result = client.read_holding_registers(address=address, count=count, device_id=device_id)
            if result is None:
                self.get_logger().error(f"读取寄存器 {hex(address)} (device_id={device_id}) 返回 None")
                return None
            if hasattr(result, 'isError') and result.isError():
                self.get_logger().error(f"读取寄存器 {hex(address)} (device_id={device_id}) 时出现错误: {result}")
                return None
            return result.registers
        except Exception as e:
            self.get_logger().error(f"读取寄存器 {hex(address)} (device_id={device_id}) 时出错: {e}")
            return None

    def open_hand(self, client, device_id, torque):
        try:
            # 按照设备协议写寄存器，所有写操作都带 device_id
            self.write_register(client, 0x0102, 0, device_id=device_id)   # 开爪命令 (0 = open)
            time.sleep(0.05)
            self.write_register(client, 0x0103, 10, device_id=device_id)  # 扭矩设置 (示例)
            time.sleep(0.05)
            self.write_register(client, 0x0105, int(torque), device_id=device_id)  # 扭矩值
            time.sleep(0.05)
            self.write_register(client, 0x0108, 1, device_id=device_id)   # 激活夹具
            return True
        except Exception as e:
            self.get_logger().error(f"打开夹爪 (device_id={device_id}) 时出错: {e}")
            return False

    def close_hand(self, client, device_id, torque):
        try:
            self.write_register(client, 0x0102, 1, device_id=device_id)   # 关爪命令 (1 = close)
            time.sleep(0.05)
            self.write_register(client, 0x0103, 10, device_id=device_id)  # 扭矩设置 (示例)
            time.sleep(0.05)
            self.write_register(client, 0x0105, int(torque), device_id=device_id)  # 扭矩值
            time.sleep(0.05)
            self.write_register(client, 0x0108, 1, device_id=device_id)   # 激活夹具
            return True
        except Exception as e:
            self.get_logger().error(f"关闭夹爪 (device_id={device_id}) 时出错: {e}")
            return False

    def position_control(self, client, device_id, torque, position, max_map):
        try:
            # position 为 0~100 百分比，转换为设备的映射
            position_write = int((position / 100.0) * max_map) if max_map else int(position)
            # 不同设备协议可能需要不同寄存器，这里按原逻辑写入（如需调整请修改寄存器地址）
            self.write_register(client, 0x0102, 0, device_id=device_id)   # 关爪/进入位置控制命令
            time.sleep(0.05)
            self.write_register(client, 0x0103, position_write, device_id=device_id)  # 写入位置值（或其他含义）
            time.sleep(0.05)
            self.write_register(client, 0x0105, int(torque), device_id=device_id)  # 扭矩值
            time.sleep(0.05)
            self.write_register(client, 0x0108, 1, device_id=device_id)   # 激活
            return True
        except Exception as e:
            self.get_logger().error(f"位置控制 (device_id={device_id}) 时出错: {e}")
            return False

    def execute_callback(self, goal_handle):
        self.get_logger().info('收到一个新的目标请求')

        goal = goal_handle.request
        arm = goal.arm       # 目标中指定的臂（left 或 right）
        method = goal.method # 目标中指定的动作（open / close / position）
        torque = goal.torque
        position = goal.position
        feedback_msg = GripperAction.Feedback()
        result = GripperAction.Result()

        self.get_logger().info(f"操作臂: {arm}, 动作: {method}, 扭矩: {torque}, 位置：{position}")

        client, device_id, max_map = self.get_client(arm)
        if client is None:
            self.get_logger().error("无法获取对应的 Modbus 客户端")
            result.success = False
            result.gripper_status = '失败'
            result.gripper_message = "无法获取对应的Modbus客户端"
            goal_handle.succeed()
            return result

        # 根据目标选择打开或关闭夹爪（现在都传 device_id）
        if method == 'open':
            success = self.open_hand(client, device_id, torque)
            action = '打开'
        elif method == 'close':
            success = self.close_hand(client, device_id, torque)
            action = '关闭'
        elif method == 'position':
            success = self.position_control(client, device_id, torque, position, max_map)
            action = '位置控制'
        else:
            self.get_logger().error(f"未知的操作命令: {method}")
            result.success = False
            result.gripper_status = '失败'
            result.gripper_message = f"未知的操作命令: {method}"
            goal_handle.succeed()
            return result

        if not success:
            self.get_logger().error(f"夹具{action}失败 (device_id={device_id})")
            result.success = False
            result.gripper_status = '失败'
            result.gripper_message = f"夹具{action}失败"
            goal_handle.succeed()
            return result

        self.get_logger().info(f"夹具成功{action} (device_id={device_id})，扭矩设置为 {torque}")

        # 启动超时计时器
        start_time = time.time()
        timeout_seconds = 3.0

        # 循环查询执行器状态
        while True:
            # 检查是否超时
            elapsed = time.time() - start_time
            if elapsed > timeout_seconds:
                self.get_logger().error("3秒内未检测到到达信号，动作超时失败")
                result.success = False
                result.gripper_status = '超时失败'
                result.gripper_message = "在3秒内未检测到动作完成信号"
                goal_handle.succeed()
                return result

            if method == 'close':
                # 读取力矩
                torque_regs = self.read_register(client, 0x0601, count=1, device_id=device_id)
                # 读取位置
                pos_regs = self.read_register(client, 0x0602, count=1, device_id=device_id)

                if torque_regs is None or pos_regs is None:
                    time.sleep(0.1)
                    continue

                # 力矩到达（=1） 或 位置到达（=1）
                arrived = (torque_regs[0] == 1) or (pos_regs[0] == 1)

            else:
                # 原逻辑：只检查位置
                arrived_regs = self.read_register(client, 0x0602, count=1, device_id=device_id)

                if arrived_regs is None:
                    time.sleep(0.1)
                    continue

                arrived = (arrived_regs[0] == 1)
                
            # 读取位置与扭矩信息
            pos_high_regs = self.read_register(client, 0x060D, count=1, device_id=device_id)
            pos_low_regs = self.read_register(client, 0x060E, count=1, device_id=device_id)
            current_torque_regs = self.read_register(client, 0x060C, count=1, device_id=device_id)

            if pos_high_regs is None or pos_low_regs is None:
                # 读取失败时稍等后重试
                time.sleep(0.1)
                continue

            pos_high = pos_high_regs[0]
            pos_low = pos_low_regs[0]
            current_position = (pos_high << 16) + pos_low

            # 通过 feedback 返回当前的位置(转换为float类型)
            feedback_msg.current_position = float(current_position)
            feedback_msg.gripper_status = '执行中'
            feedback_msg.gripper_message = f"当前位置: {current_position}"
            self.get_logger().debug(f"[device_id={device_id}] 当前位置: {current_position}")
            self.get_logger().debug(f"[device_id={device_id}] 当前电流/扭矩寄存器: {current_torque_regs}")

            goal_handle.publish_feedback(feedback_msg)

            # 判断到达条件
            if arrived == 1:
                if method == 'close':
                    self.get_logger().info(f"[device_id={device_id}] 力矩到达，动作完成")
                else:
                    self.get_logger().info(f"[device_id={device_id}] 位置到达，动作完成")

                result.success = True
                result.gripper_status = '成功'
                result.gripper_message = f"夹具成功{action}"
                goal_handle.succeed()
                return result

            time.sleep(0.1)

    def destroy_node(self):
        # 销毁 action server 并关闭 modbus 连接
        try:
            self._action_server.destroy()
        except Exception:
            pass
        try:
            self.client.close()
        except Exception:
            pass
        self.get_logger().info("Modbus 连接已关闭，Action 服务器已销毁")
        super().destroy_node()

def main(args=None):
    rclpy.init(args=args)
    action_server = GripperActionServer()

    try:
        executor = MultiThreadedExecutor()
        rclpy.spin(action_server, executor=executor)
    except KeyboardInterrupt:
        action_server.get_logger().info("节点已停止")
    finally:
        action_server.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()