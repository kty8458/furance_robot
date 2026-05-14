import numpy as np

# --- 输入你刚才的数据 ---
# Translation (xyz)
t_in = np.array([-1.273421926882106, -0.21851317616657565, -0.2298900817166826])
# Rotation (xyzw)
q_in = np.array([0.3021911749236066, 0.24530455464501538, 0.6310514949235648, 0.6710291946133452])

def get_inverse_transform(t, q):
    # 1. 构造旋转矩阵
    x, y, z, w = q
    R = np.array([
        [1 - 2*y**2 - 2*z**2,  2*x*y - 2*z*w,      2*x*z + 2*y*w],
        [2*x*y + 2*z*w,      1 - 2*x**2 - 2*z**2,  2*y*z - 2*x*w],
        [2*x*z - 2*y*w,      2*y*z + 2*x*w,      1 - 2*x**2 - 2*y**2]
    ])
    
    # 2. 构造 4x4 齐次矩阵
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = t
    
    # 3. 求逆矩阵
    T_inv = np.linalg.inv(T)
    
    # 4. 提取结果
    t_out = T_inv[:3, 3]
    
    # 从旋转矩阵提取四元数 (简化版逻辑)
    # 注：实际中四元数逆可以直接通过共轭求得: [-x, -y, -z, w]，这里为了验证矩阵运算保持一致
    R_inv = T_inv[:3, :3]
    tr = R_inv.trace()
    if tr > 0:
        S = np.sqrt(tr + 1.0) * 2
        qw = 0.25 * S
        qx = (R_inv[2,1] - R_inv[1,2]) / S
        qy = (R_inv[0,2] - R_inv[2,0]) / S
        qz = (R_inv[1,0] - R_inv[0,1]) / S
    else:
        # 简单回退策略，直接利用性质：逆四元数 = [-x, -y, -z, w]
        qx, qy, qz, qw = -x, -y, -z, w

    return t_out, [qx, qy, qz, qw]

# 计算
pos_res, quat_res = get_inverse_transform(t_in, q_in)

print("-" * 30)
print("【Marker 到 末端】的变换 (Marker -> Eed):")
print(f"Translation (xyz): {list(pos_res)}")
print(f"Rotation (xyzw):   {list(quat_res)}")
print("-" * 30)