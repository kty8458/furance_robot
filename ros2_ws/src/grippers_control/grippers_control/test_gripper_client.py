import rclpy
from gripper_action_client import GripperActionClient


def main():
    rclpy.init()

    client = GripperActionClient()

    # 示例参数
    arm = "left"
    method = "close"
    torque = 80.0
    position = 50.0

    result = client.send_goal(arm, method, torque, position)

    if result:
        print("=== Action Result ===")
        print("status:", client._gripper_status)
        print("message:", client._gripper_feedback)

    client.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
