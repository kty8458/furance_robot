import rclpy
from rclpy.node import Node
from pymodbus.client import ModbusSerialClient
import time

class GripperServiceNode(Node):
    def __init__(self):
        super().__init__('gripper_test_node')

        # 初始化 Modbus 客户端
        self.client = ModbusSerialClient(
            port='/dev/ttyUSB0',
            baudrate=115200,
            timeout=1,
            parity='N',
            stopbits=1,
            bytesize=8
        )

        while not self.client.connect():
            self.get_logger().error("无法连接到 Modbus 设备")
            time.sleep(0.5)

        self.get_logger().info("成功连接到 Modbus 设备")

    def write_register(self, address, value, unit=1):
        try:
            result = self.client.write_register(address, value, slave=unit)
            if result.isError():
                return False
            return True
        except Exception as e:
            self.get_logger().error(f"写入寄存器时出错: {e}")
            return False

    def open_hand(self, torque):
        try:
            self.write_register(0x0102, 0)  # 发送开爪命令
            time.sleep(0.1)
            self.write_register(0x0103, 10)  # 扭矩设置
            time.sleep(0.1)
            self.write_register(0x0105, torque)  # 扭矩值
            time.sleep(0.1)
            self.write_register(0x0108, 1)  # 激活夹具
            return True
        except Exception as e:
            self.get_logger().error(f"打开夹爪时出错: {e}")
            return False

    def close_hand(self, torque):
        try:
            self.write_register(0x0102, 1)  # 发送关爪命令
            time.sleep(0.1)
            self.write_register(0x0103, 10)  # 扭矩设置
            time.sleep(0.1)
            self.write_register(0x0105, torque)  # 扭矩值
            time.sleep(0.1)
            self.write_register(0x0108, 1)  # 激活夹具
            return True
        except Exception as e:
            self.get_logger().error(f"关闭夹爪时出错: {e}")
            return False

    def destroy_node(self):
        self.client.close()
        self.get_logger().info("Modbus 连接已关闭")
        super().destroy_node()

    def manual_control(self):
        while True:
            print("\n请选择操作：")
            print("1. 打开夹具")
            print("2. 关闭夹具")
            print("3. 退出")

            try:
                choice = input("请输入操作（1/2/3）：")
                if choice == "1":
                    torque = input("请输入力矩：")
                    if self.open_hand(torque):
                        self.get_logger().info(f"夹具成功打开，扭矩设置为 {torque}")
                    else:
                        self.get_logger().error("夹具打开失败")
                elif choice == "2":
                    torque = input("请输入力矩：")
                    if self.close_hand(torque):
                        self.get_logger().info(f"夹具成功关闭，扭矩设置为 {torque}")
                    else:
                        self.get_logger().error("夹具关闭失败")
                elif choice == "3":
                    print("退出程序...")
                    break
                else:
                    print("无效的选择，请重新输入")
            except ValueError:
                print("请输入有效的数字！")

def main(args=None):
    rclpy.init(args=args)
    node = GripperServiceNode()

    try:
        node.manual_control()
    except KeyboardInterrupt:
        node.get_logger().info("节点已停止")
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
