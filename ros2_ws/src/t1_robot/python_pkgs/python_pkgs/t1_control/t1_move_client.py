import rclpy
from rclpy.node import Node
from control_interfaces.srv import MoveP, MoveL
from geometry_msgs.msg import PoseStamped
from geometry_msgs.msg import Pose


class MovePClient(Node):
    def __init__(self):
        super().__init__("movep_client")
        self.cli = self.create_client(MoveP, "move_pose")

        while not self.cli.wait_for_service(timeout_sec=1.0):
            self.get_logger().info("Waiting for move_pose service...")

    def send_request(self, lor, pose, to_frame, reference_frame, planner):
        req = MoveP.Request()
        req.lor = lor
        req.target_pose = pose
        req.to_frame = to_frame
        req.reference_frame = reference_frame
        req.planner = planner

        future = self.cli.call_async(req)
        rclpy.spin_until_future_complete(self, future)

        if future.result() is not None:
            return future.result()
        else:
            raise RuntimeError("Service call failed")


def build_pose(x, y, z, qx, qy, qz, qw, frame_id="base_link"):
    pose = PoseStamped()
    pose.header.frame_id = frame_id
    pose.pose.position.x = x
    pose.pose.position.y = y
    pose.pose.position.z = z
    pose.pose.orientation.x = qx
    pose.pose.orientation.y = qy
    pose.pose.orientation.z = qz
    pose.pose.orientation.w = qw
    return pose


class MoveLClient(Node):
    def __init__(self):
        super().__init__("movel_client")
        self.cli = self.create_client(MoveL, "move_line")

        while not self.cli.wait_for_service(timeout_sec=1.0):
            self.get_logger().info("Waiting for move_line service...")

    def send_request(self, lor, waypoints):
        req = MoveL.Request()
        req.lor = lor
        req.waypoints = waypoints

        future = self.cli.call_async(req)
        rclpy.spin_until_future_complete(self, future)

        if future.result() is not None:
            return future.result()
        else:
            raise RuntimeError("Service call failed")


def main():
    rclpy.init()
    movep = MovePClient()

    pose = build_pose(
        x=0.36, y=0.2, z=0.11,
        qx=-0.5, qy=0.5, qz=-0.5, qw=0.5,
        frame_id="base_link"
    )

    resp = movep.send_request(
        lor="left",
        pose=pose,
        to_frame="ARM-L-J7_Link",
        reference_frame="base_link",
        planner="ompl"
    )

    print("MoveP response:", resp.success, resp.message)
    rclpy.shutdown()


if __name__ == "__main__":
    main()
