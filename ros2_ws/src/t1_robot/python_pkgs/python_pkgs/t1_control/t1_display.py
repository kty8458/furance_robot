import rclpy
from rclpy.node import Node
from interface_pkg.srv import MoveToJointPositions, ClearError, RobotEnableControl
import time


class Display(Node):
    def __init__(self):
        super().__init__('display')
        self.move_client = self.create_client(MoveToJointPositions, '/move_joint_positions')
        while not self.move_client.wait_for_service(timeout_sec=3.0):
            print("双臂控制服务未上线！")
        self.joint_states_group = [
            [[0.0, 0.0, 0.0, -90.0, 0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 90.0, 0.0, 0.0, 0.0]],
            [[-25.4, 0.0, -9.0, -94.0, -87.0, -48.8, 174.0], [0.0, 0.0, 0.0, 90.0, 0.0, 0.0, 0.0]],
            [[-25.4, 0.0, 20.0, -94.0, -87.0, -48.8, 174.0], [0.0, 0.0, 0.0, 90.0, 0.0, 0.0, 0.0]],
            [[-25.4, 0.0, -20.0, -94.0, -87.0, -48.8, 174.0], [0.0, 0.0, 0.0, 90.0, 0.0, 0.0, 0.0]],
            [[0.0, 0.0, 0.0, -90.0, 0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 90.0, 0.0, 0.0, 0.0]]
        ]

    def done_callback(self, fut):
        try:
            res = fut.result()
            if res.success:
                print(f"执行成功: {res.message}")
            else:
                print(f"执行失败: {res.message}")
        except Exception as e:
            print(f"服务调用异常: {e}")

    def moveToTargetEvent(self, num):
        try:
            req = MoveToJointPositions.Request()
            left_joints, right_joints = self.joint_states_group[num][0], self.joint_states_group[num][1]
            req.left_joints = left_joints
            req.right_joints = right_joints
            future = self.move_client.call_async(req)
            future.add_done_callback(self.done_callback)
        except Exception as e:
            print(f"异常,执行出错: {e}")

    def execute_loop(self):
        print('start')
        while rclpy.ok():
            for i in range(len(self.joint_states_group)):
                print(i)
                self.moveToTargetEvent(i)
            time.sleep(10.0)


def main(args=None):
    rclpy.init(args=args)
    node = Display()
    try:
        node.execute_loop()
    except Exception as e:
        print(f"异常,执行出错: {e}")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
