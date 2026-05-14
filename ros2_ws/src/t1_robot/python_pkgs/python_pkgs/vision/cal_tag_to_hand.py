import rclpy
from rclpy.node import Node
from rclpy.duration import Duration
from tf2_ros import Buffer, TransformListener
import numpy as np
import time
import threading

# --- 辅助函数：四元数/位置 转 4x4矩阵 ---
def pose_to_matrix(pos, quat):
    """
    pos: [x, y, z]
    quat: [x, y, z, w]
    return: 4x4 numpy matrix
    """
    x, y, z = pos
    qx, qy, qz, qw = quat
    
    # 构造旋转矩阵 (根据四元数公式)
    # R = ...
    R = np.array([
        [1 - 2*qy**2 - 2*qz**2,  2*qx*qy - 2*qz*qw,      2*qx*qz + 2*qy*qw],
        [2*qx*qy + 2*qz*qw,      1 - 2*qx**2 - 2*qz**2,  2*qy*qz - 2*qx*qw],
        [2*qx*qz - 2*qy*qw,      2*qy*qz + 2*qx*qw,      1 - 2*qx**2 - 2*qy**2]
    ])
    
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = [x, y, z]
    return T

# --- 辅助函数：4x4矩阵 转 四元数/位置 ---
def matrix_to_pose(matrix):
    """
    return: (pos=[x,y,z], quat=[x,y,z,w])
    """
    T = matrix
    x, y, z = T[:3, 3]
    
    # 从旋转矩阵提取四元数
    # 这里使用简化的转换逻辑，实际工程建议使用 transforms3d 或 scipy.spatial.transform
    tr = T[0,0] + T[1,1] + T[2,2]
    if tr > 0:
        S = np.sqrt(tr + 1.0) * 2
        qw = 0.25 * S
        qx = (T[2,1] - T[1,2]) / S
        qy = (T[0,2] - T[2,0]) / S
        qz = (T[1,0] - T[0,1]) / S
    elif (T[0,0] > T[1,1]) and (T[0,0] > T[2,2]):
        S = np.sqrt(1.0 + T[0,0] - T[1,1] - T[2,2]) * 2
        qw = (T[2,1] - T[1,2]) / S
        qx = 0.25 * S
        qy = (T[0,1] + T[1,0]) / S
        qz = (T[0,2] + T[2,0]) / S
    elif T[1,1] > T[2,2]:
        S = np.sqrt(1.0 + T[1,1] - T[0,0] - T[2,2]) * 2
        qw = (T[0,2] - T[2,0]) / S
        qx = (T[0,1] + T[1,0]) / S
        qy = 0.25 * S
        qz = (T[1,2] + T[2,1]) / S
    else:
        S = np.sqrt(1.0 + T[2,2] - T[0,0] - T[1,1]) * 2
        qw = (T[1,0] - T[0,1]) / S
        qx = (T[0,2] + T[2,0]) / S
        qy = (T[1,2] + T[2,1]) / S
        qz = 0.25 * S
        
    return [x, y, z], [qx, qy, qz, qw]


class CalibrationTool(Node):
    def __init__(self):
        super().__init__('calibration_tool_node')
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.get_logger().info("Calibration Tool Initialized.")

    def get_averaged_tf(self, target_frame, source_frame, samples=100, interval=0.05):
        """
        这里复用之前的核心均值滤波代码
        """
        collected_pos = []
        collected_quat = []
        
        self.get_logger().info(f"Sampling {samples} times: {source_frame} -> {target_frame}")
        
        count = 0
        while count < samples:
            try:
                t = self.tf_buffer.lookup_transform(target_frame, source_frame, rclpy.time.Time(), timeout=Duration(seconds=1.0))
                p = t.transform.translation
                q = t.transform.rotation
                collected_pos.append([p.x, p.y, p.z])
                collected_quat.append([q.x, q.y, q.z, q.w])
                count += 1
                time.sleep(interval)
            except Exception as e:
                self.get_logger().warning(f"Lookup failed: {e}")
                time.sleep(0.1)
                continue
        
        if not collected_pos: return None, None

        # 转换为numpy
        pos_array = np.array(collected_pos)
        quat_array = np.array(collected_quat)

        # 四元数对齐 (防止 +-q 问题)
        base_q = quat_array[0]
        for i in range(1, len(quat_array)):
            if np.dot(quat_array[i], base_q) < 0:
                quat_array[i] = -quat_array[i]

        # 去除异常值 (Mean +/- 2*Std)
        pos_mean = np.mean(pos_array, axis=0)
        pos_std = np.std(pos_array, axis=0)
        mask = np.all(np.abs(pos_array - pos_mean) < 2 * pos_std + 1e-6, axis=1) # +1e-6防止std为0
        
        filtered_pos = pos_array[mask]
        filtered_quat = quat_array[mask]
        
        if len(filtered_pos) == 0: return None, None

        final_pos = np.mean(filtered_pos, axis=0)
        avg_quat = np.mean(filtered_quat, axis=0)
        final_quat = avg_quat / np.linalg.norm(avg_quat)

        return list(final_pos), list(final_quat)

    def compute_fixed_transform(self, base_frame, eed_frame, marker_frame):
        """
        执行你描述的完整业务流程
        """
        print("\n" + "="*50)
        print("步骤 2: 示教环节")
        print(f"请手动移动机器人，使 [{eed_frame}] 对齐/接触到 Marker。")
        input(">>> 移动完成后，请按 [Enter] 键继续...")
        print("="*50)
        
        # 2. 获取 Eed -> Base 的变换 (T_base_eed)
        e_pos, e_quat = self.get_averaged_tf(base_frame, eed_frame)
        
        if e_pos is None:
            self.get_logger().error("无法获取末端坐标，任务终止。")
            return
        input(">>> 移动完成后，请按 [Enter] 键继续...")
        print("="*50)
        print(f"检测到末端坐标: {np.round(e_pos, 4), np.round(e_quat, 4)}")
        print("\n" + "="*50)
        print("步骤 1: 正在计算 Marker 在 Base 下的坐标...")
        print("请保持 Camera 和 Marker 静止。")
        print("="*50)
        
        # 1. 获取 Marker -> Base 的变换 (T_base_marker)
        # lookup_transform(target, source) -> transform source IN target
        m_pos, m_quat = self.get_averaged_tf(base_frame, marker_frame)
        
        if m_pos is None:
            self.get_logger().error("无法获取 Marker 坐标，任务终止。")
            return

        print(f"检测到 Marker 坐标: {np.round(m_pos, 4), np.round(m_quat, 4)}")
        

        # 3. 矩阵运算
        # T_base_marker
        T_bm = pose_to_matrix(m_pos, m_quat)
        # T_base_eed
        T_be = pose_to_matrix(e_pos, e_quat)
        
        # 目标: T_eed_marker = inv(T_base_eed) * T_base_marker
        try:
            T_be_inv = np.linalg.inv(T_be)
            T_em = np.dot(T_be_inv, T_bm)
            T_em = np.linalg.inv(T_em)
            
            # 转回 pos, quat
            res_pos, res_quat = matrix_to_pose(T_em)
            
            print("\n" + "#"*50)
            print("计算结果: 末端到 Marker 的固定变换 (T_eed_marker)")
            print("#"*50)
            print(f"Translation (xyz): {res_pos}")
            print(f"Rotation (xyzw):   {res_quat}")
            print("#"*50)
            
            return res_pos, res_quat
            
        except np.linalg.LinAlgError:
            self.get_logger().error("矩阵求逆失败！")
            return None

def main():
    rclpy.init()
    node = CalibrationTool()
    
    # 后台线程处理 TF
    executor = rclpy.executors.MultiThreadedExecutor()
    executor.add_node(node)
    spin_thread = threading.Thread(target=executor.spin, daemon=True)
    spin_thread.start()

    try:
        # 定义坐标系名称 (请根据实际情况修改)
        BASE_LINK = "base_link"
        EED_LINK = "J7_right_Link"       
        CAMERA_MARKER = "camera_marker" 

        # 执行功能
        node.compute_fixed_transform(BASE_LINK, EED_LINK, CAMERA_MARKER)

    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()