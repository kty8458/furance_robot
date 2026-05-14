#人形机器人上肢开发记录1：配置moveit2

## 开发环境
人形机器人：宇树h1_2
上位机：Nvidia Jetson orin nx 16G
系统： Jetpack6.0（ubuntu22.04）
ROS：ROS2 humble

## moveit2配置
moveit2的配置助手非常方便,在完成安装后运行以下指令运行
```bash
 ros2 run moveit_setup_assistant moveit_setup_assistant
```
主要配置流程参考鱼香ROS的博客，本文不再赘述，只记录几个注意点
鱼香ROSmoveit2链接：https://blog.csdn.net/qq_27865227/article/details/126860096
### 1.准备urdf/xacro：
准备的xacro或者urdf必须放置在已经编译好的ROSpackage里，配置助手不会直接读取urdf文件的地址而是根据pakckage寻找，如果只是在普通目录下配置助手会报错
### 2.修改urdf/xacro：
人形机器人不同于机械臂，除了手臂关节以外还有双腿、灵巧手等其他关节，在我们的项目中双腿的joint_states会一直发布，灵巧手是单独的控制方式，不发布joint_states，如果在配置moveit时选择加载了这些关节但是没有纳入规划组，在之后的运行时会遇到moveit收到了joint_states但是不知道如何处理或者moveit想要收到一些关节的joint_states但是没有收到这两种情况。

所以针对不需要的关节，如果他们会发布joint_states，比如本项目中的双腿，可以一起设置为规划组但是不去使用，或者将urdf中的关节类型改为fixed，moveit将不会考虑这些关节。
```bash
<joint name="joint" type="fixed">
```
### 3.修改配置文件
通过助手生成srdf、joint_limits.yaml、kinematics.yaml、moveit_controllers.yaml、pilz_cartesian_limits.yaml、ros2_controllers.yaml、sensors_3d.yaml这些配置文件，接下来记录一下关于配置文件的重要信息
#### 3.1 srdf
srdf是moveit特有的文件格式，记录了规划组信息、预设位置和忽略自碰撞信息，规划组信息和忽略自碰撞都依靠助手自动生成。
```bash
    <group name="left_arm">
        <joint name="left_shoulder_pitch_joint"/>
        <joint name="left_shoulder_roll_joint"/>
        <joint name="left_shoulder_yaw_joint"/>
        <joint name="left_elbow_pitch_joint"/>
        <joint name="left_elbow_roll_joint"/>
        <joint name="left_wrist_pitch_joint"/>
        <joint name="left_wrist_yaw_joint"/>
    </group>
```
也可以将两个规划组合并成一个规划组
```bash
    <group name="both_arms">
        <group name="left_arm"/>
        <group name="right_arm"/>
    </group>
```
我们可以修改srdf添加预设的位置，选择对应的规划组，指定规划组中所有关节的角度
```bash
    <group_state name="home" group="both_arms">
        <joint name="left_shoulder_pitch_joint" value="0.36" />
        <joint name="left_shoulder_roll_joint" value="0.0" />
        <joint name="left_shoulder_yaw_joint" value="0.0" />
        <joint name="left_elbow_pitch_joint" value="-0.26" />
        <joint name="left_elbow_roll_joint" value="0.0" />
        <joint name="left_wrist_pitch_joint" value="0.0" />
        <joint name="left_wrist_yaw_joint" value="0.0" />
        <joint name="right_shoulder_pitch_joint" value="0.36" />
        <joint name="right_shoulder_roll_joint" value="0.0" />
        <joint name="right_shoulder_yaw_joint" value="0.0" />
        <joint name="right_elbow_pitch_joint" value="-0.26" />
        <joint name="right_elbow_roll_joint" value="0.0" />
        <joint name="right_wrist_pitch_joint" value="0.0" />
        <joint name="right_wrist_yaw_joint" value="0.0" />
    </group_state>
```
srdf也可以用和urdf一样的方法改为xacro格式，这样可以将多个moveit_config组合起来，比如夹爪和机械臂分开配置再组合起来，moveit可以直接识别xacro作为srdf文件，封装后记得调用。
```bash
<?xml version="1.0" encoding="UTF-8"?>
<robot xmlns:xacro="http://wiki.ros.org/xacro" name="h1">

    <xacro:include filename="$(find h1_moveit_config)/config/h1.srdf.xacro" />
    <xacro:h1_srdf/>

</robot>
```
#### 3.2 joint_limits.yaml
在我的版本的moveit中存在bug，生成的joint_limits的数值为整型，但是moveit要求浮点型，需要手动将配置文件中的速度值后面加上.0。
```bash
    has_velocity_limits: true
    max_velocity: 9.0
    has_acceleration_limits: false
    max_acceleration: 0.0
```
同时RRT_Connet这类基于搜索的算法规划出来的路径可能会出现大回旋，之后会提到，所以在joint_limits里可以加入关节角度限制max/min_position，阻止某个轴旋转一整圈。
```bash
  right_shoulder_pitch_joint:
    has_velocity_limits: true
    max_velocity: 9.0
    has_acceleration_limits: false
    max_acceleration: 0.0
    min_position: -1.57 
    max_position: 1.57
```
#### 3.3 sensors_3d.yaml
sensors_3d是moveit集成的一种基于深度/点云的八叉树地图避障方法，并且可以自动过滤机器人本体，但是由于膨胀体积过大，容易将待抓取物体识别成障碍物导致规划失败，本项目暂时没有用到。
在助手生成时可以选择不生成，自己手动添加
```bash
sensors:
  - d435_depthimage
d435_depthimage:
  far_clipping_plane_distance: 5.0 #远裁剪面距离
  filtered_cloud_topic: filtered_cloud
  image_topic: /depth/image_raw #订阅的深度图像话题
  max_update_rate: 1.0 #最大地图更新频率，实时性要求高时增大
  near_clipping_plane_distance: 0.3 #近裁剪面距离
  padding_offset: 0.1 #基础膨胀偏移量	
  padding_scale: 2.0 #障碍物膨胀缩放系数	
  queue_size: 5
  sensor_plugin: occupancy_map_monitor/DepthImageOctomapUpdater
  shadow_threshold: 0.2 #阴影检测阈值，值越小误检越少
```
#### 3.4 *.ros2_control.xacro
对接ros2_control接口，在其中可以指定对应的硬件，本项目对接自己实现的控制器，使用和gazebo相同的接口，助手自动生成的代码此处是FakeSystem，不需要对接硬件或者仿真环境，可以用作简单测试。
```bash
<hardware>
    <plugin>gazebo_ros2_control/GazeboSystem</plugin>
</hardware>
```
### 4.launch文件编写
接下来是用于启动项目的launch编写，笔者在这里踩了不少坑，launch文件修修改改，所以比较乱，其实就分成三个部分move_group节点、rviz节点和robot_state节点。
这部分代码没有放完整的在这里，直接组合起来是用不了的，在实际使用过对ros2的luaunch文件和moveit的launch有一定了解后可作参考。
#### 4.1 move_group节点
由于涉及到很多改动，所以有些参数的加载设成了可改动的，有些又写死了，看上去比较乱，但笔者懒得改，在这里讲解一下
这里指定了xacro文件、moveit文件的package为h1_moveit_config，由于笔者懒，所以将desciption从原来的文件夹移到这一块来了
然后指定了urdf、srdf和joint_limits，至于为什么这些没有写死，忘了。
```bash
declared_arguments.append(
    DeclareLaunchArgument(
        "description_package",
        default_value="h1_moveit_config",
        description="Description package with robot URDF/XACRO files. Usually the argument \
    is not set, it enables use of a custom description.",
    )
)
declared_arguments.append(
    DeclareLaunchArgument(
        "description_file",
        default_value="h1.urdf.xacro",
        description="URDF/XACRO description file with the robot.",
    )
)
declared_arguments.append(
    DeclareLaunchArgument(
        "moveit_config_package",
        default_value="h1_moveit_config",
        description="MoveIt config package with robot SRDF/XACRO files. Usually the argument \
    is not set, it enables use of a custom moveit config.",
    )
)
declared_arguments.append(
    DeclareLaunchArgument(
        "moveit_config_file",
        default_value="h1_real.srdf.xacro",
        description="MoveIt SRDF/XACRO description file with the robot.",
    )
)
declared_arguments.append(
    DeclareLaunchArgument(
        "moveit_joint_limits_file",
        default_value="joint_limits.yaml",
        description="MoveIt joint limits that augment or override the values from the URDF robot_description.",
    )
)
```
接下来是加载并组织这些文件
```bash
description_package = LaunchConfiguration("description_package")
description_file = LaunchConfiguration("description_file")
moveit_config_package = LaunchConfiguration("moveit_config_package")
moveit_joint_limits_file = LaunchConfiguration("moveit_joint_limits_file")
moveit_config_file = LaunchConfiguration("moveit_config_file")
prefix = LaunchConfiguration("prefix")
use_sim_time = LaunchConfiguration("use_sim_time")
launch_rviz = LaunchConfiguration("launch_rviz")


# 加载urdf
robot_description_content = Command(
    [
        PathJoinSubstitution([FindExecutable(name="xacro")]),
        " ",
        PathJoinSubstitution([FindPackageShare(description_package), "config", description_file]),
    ]
)
robot_description = {"robot_description": robot_description_content}

# 加载srdf
robot_description_semantic_content = Command(
    [
        PathJoinSubstitution([FindExecutable(name="xacro")]),
        " ",
        PathJoinSubstitution(
            [FindPackageShare(moveit_config_package), "config", moveit_config_file]
        ),
    ]
)
robot_description_semantic = {"robot_description_semantic": ParameterValue(robot_description_semantic_content, value_type=str)}

# 加载运动学配置文件
robot_description_kinematics = PathJoinSubstitution(
    [FindPackageShare(moveit_config_package), "config", "kinematics.yaml"]
)

# 加载joint_limits
robot_description_planning = {
    "robot_description_planning": load_yaml(
        str(moveit_config_package.perform(context)),
        os.path.join("config", str(moveit_joint_limits_file.perform(context))),
    )
}

# 加载八叉树地图视觉避障文件
octomap_config = {'octomap_resolution': 0.01}

octomap_updater_config = load_yaml("h1_moveit_config", "config/sensors_3d.yaml")


# 加载OMPL规划器
ompl_planning_pipeline_config = {
        "planning_plugin": "ompl_interface/OMPLPlanner",
        "request_adapters": """default_planner_request_adapters/AddTimeOptimalParameterization 
                            default_planner_request_adapters/FixWorkspaceBounds 
                            default_planner_request_adapters/FixStartStateBounds 
                            default_planner_request_adapters/FixStartStateCollision 
                            default_planner_request_adapters/FixStartStatePathConstraints""",
        "start_state_max_bounds_error": 0.1,
}

ompl_planning_yaml = load_yaml("h1_moveit_config", "config/ompl_planning.yaml")
ompl_planning_pipeline_config.update(ompl_planning_yaml)

# 加载cuMotion规划器，之后会讲到，这里和ompl同等地位，可以不用 
cumotion_config_file_path = os.path.join(
    get_package_share_directory('isaac_ros_cumotion_moveit'),
    'config',
    'isaac_ros_cumotion_planning.yaml'
)
with open(cumotion_config_file_path) as cumotion_config_file:
    cumotion_config = yaml.safe_load(cumotion_config_file)

planning_pipelines = {}
# 加载两个不同的规划器
planning_pipelines['planning_pipelines'] = ["isaac_ros_cumotion", "ompl"]
planning_pipelines['default_planning_pipeline'] = "ompl"
planning_pipelines['isaac_ros_cumotion'] = cumotion_config
planning_pipelines['ompl'] = ompl_planning_pipeline_config


# 加载moveit_controllers
controllers_yaml = load_yaml("h1_moveit_config", "config/moveit_controllers.yaml")

moveit_controllers = {
    "moveit_simple_controller_manager": controllers_yaml,
    "moveit_controller_manager": "moveit_simple_controller_manager/MoveItSimpleControllerManager",
    "trajectory_execution" : {
        "allowed_execution_duration_scaling": 2.0,  # change execution time scaling here
        "allowed_goal_duration_margin": 0.5,
        "allowed_start_tolerance": 0.01,
    }
}

trajectory_execution = {
    "moveit_manage_controllers": False,
    "trajectory_execution.allowed_execution_duration_scaling": 1.2,
    "trajectory_execution.allowed_goal_duration_margin": 0.5,
    "trajectory_execution.allowed_start_tolerance": 0.01,
}

planning_scene_monitor_parameters = {
    "publish_planning_scene": True,
    "publish_geometry_updates": True,
    "publish_state_updates": True,
    "publish_transforms_updates": True,
    "publish_robot_description":True,
    "publish_robot_description_semantic":True,
}
```
加载参数后初始化节点,都是上面提到的参数
```bash
move_group_node = Node(
        package="moveit_ros_move_group",
        executable="move_group",
        output="screen",
        parameters=[
            robot_description,
            robot_description_semantic,
            robot_description_kinematics,
            robot_description_planning,
            octomap_config,
            octomap_updater_config,
            planning_pipelines,
            trajectory_execution,
            moveit_controllers,
            planning_scene_monitor_parameters,
            {"use_sim_time": use_sim_time},
        ]
    )

```
#### 4.2 其他节点
rviz可视化界面，同样需要上面的参数
```bash
 rviz_config_file = PathJoinSubstitution(
        [FindPackageShare(moveit_config_package), "config", "moveit.rviz"]
    )
rviz_node = Node(
    package="rviz2",
    condition=IfCondition(launch_rviz),
    executable="rviz2",
    name="rviz2_moveit",
    output="log",
    arguments=["-d", rviz_config_file],
    parameters=[
        robot_description,
        robot_description_semantic,
        planning_pipelines,
        robot_description_kinematics,
        robot_description_planning,
    ],
)
```
robot_state_publisher只需要加载urdf，用于发布tf话题，方便查找坐标变换
```bash
node_robot_state_publisher = Node(
    package='robot_state_publisher',
    executable='robot_state_publisher',
    parameters=[robot_description],
    output='screen'
)
```
## 最后附上我的launch的完整代码
```bash
# Copyright (c) 2021 PickNik, Inc.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#    * Redistributions of source code must retain the above copyright
#      notice, this list of conditions and the following disclaimer.
#
#    * Redistributions in binary form must reproduce the above copyright
#      notice, this list of conditions and the following disclaimer in the
#      documentation and/or other materials provided with the distribution.
#
#    * Neither the name of the {copyright_holder} nor the names of its
#      contributors may be used to endorse or promote products derived from
#      this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

#
# Author: Denis Stogl

import os

from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.conditions import IfCondition
from launch.substitutions import Command, FindExecutable, LaunchConfiguration, PathJoinSubstitution
from launch_ros.parameter_descriptions import ParameterValue

import math
import os
import yaml

from ament_index_python.packages import get_package_share_directory

def construct_angle_radians(loader, node):
    """Utility function to construct radian values from yaml."""
    value = loader.construct_scalar(node)
    try:
        return float(value)
    except SyntaxError:
        raise Exception("invalid expression: %s" % value)


def construct_angle_degrees(loader, node):
    """Utility function for converting degrees into radians from yaml."""
    return math.radians(construct_angle_radians(loader, node))


def load_yaml(package_name, file_path):
    package_path = get_package_share_directory(package_name)
    absolute_file_path = os.path.join(package_path, file_path)

    try:
        yaml.SafeLoader.add_constructor("!radians", construct_angle_radians)
        yaml.SafeLoader.add_constructor("!degrees", construct_angle_degrees)
    except Exception:
        raise Exception("yaml support not available; install python-yaml")

    try:
        with open(absolute_file_path) as file:
            return yaml.safe_load(file)
    except OSError:  # parent of IOError, OSError *and* WindowsError where available
        return None


def load_yaml_abs(absolute_file_path):
    try:
        yaml.SafeLoader.add_constructor("!radians", construct_angle_radians)
        yaml.SafeLoader.add_constructor("!degrees", construct_angle_degrees)
    except Exception:
        raise Exception("yaml support not available; install python-yaml")

    try:
        with open(absolute_file_path) as file:
            return yaml.safe_load(file)
    except OSError:  # parent of IOError, OSError *and* WindowsError where available
        return None

def launch_setup(context, *args, **kwargs):

    # General arguments
    description_package = LaunchConfiguration("description_package")
    description_file = LaunchConfiguration("description_file")
    moveit_config_package = LaunchConfiguration("moveit_config_package")
    moveit_joint_limits_file = LaunchConfiguration("moveit_joint_limits_file")
    moveit_config_file = LaunchConfiguration("moveit_config_file")
    prefix = LaunchConfiguration("prefix")
    use_sim_time = LaunchConfiguration("use_sim_time")
    launch_rviz = LaunchConfiguration("launch_rviz")


    robot_description_content = Command(
        [
            PathJoinSubstitution([FindExecutable(name="xacro")]),
            " ",
            PathJoinSubstitution([FindPackageShare(description_package), "config", description_file]),
        ]
    )
    robot_description = {"robot_description": robot_description_content}

    # MoveIt Configuration
    robot_description_semantic_content = Command(
        [
            PathJoinSubstitution([FindExecutable(name="xacro")]),
            " ",
            PathJoinSubstitution(
                [FindPackageShare(moveit_config_package), "config", moveit_config_file]
            ),
        ]
    )
    robot_description_semantic = {"robot_description_semantic": ParameterValue(robot_description_semantic_content, value_type=str)}

    robot_description_kinematics = PathJoinSubstitution(
        [FindPackageShare(moveit_config_package), "config", "kinematics.yaml"]
    )

    robot_description_planning = {
        "robot_description_planning": load_yaml(
            str(moveit_config_package.perform(context)),
            os.path.join("config", str(moveit_joint_limits_file.perform(context))),
        )
    }

    #octomap_config = {'octomap_resolution': 0.01}

    #octomap_updater_config = load_yaml("h1_moveit_config", "config/sensors_3d.yaml")

    # Planning Configuration
    # ompl_planning_pipeline_config = {
    #     "move_group": {
    #         "planning_plugin": "ompl_interface/OMPLPlanner",
    #         "request_adapters": """default_planner_request_adapters/AddTimeOptimalParameterization default_planner_request_adapters/FixWorkspaceBounds default_planner_request_adapters/FixStartStateBounds default_planner_request_adapters/FixStartStateCollision default_planner_request_adapters/FixStartStatePathConstraints""",
    #         "start_state_max_bounds_error": 0.1,
    #     }
    # }
    # ompl_planning_yaml = load_yaml("h1_moveit_config", "config/ompl_planning.yaml")
    # ompl_planning_pipeline_config["move_group"].update(ompl_planning_yaml)
    # cumotion_config_file_path = os.path.join(
    #     get_package_share_directory('isaac_ros_cumotion_moveit'),
    #     'config',
    #     'isaac_ros_cumotion_planning.yaml'
    # )
    # with open(cumotion_config_file_path) as cumotion_config_file:
    #     cumotion_config = yaml.safe_load(cumotion_config_file)
    # ompl_planning_pipeline_config['move_group']['planning_pipelines'] = "ompl,isaac_ros_cumotion"
    # ompl_planning_pipeline_config['move_group']['isaac_ros_cumotion'] = cumotion_config
    
    # Planning Configuration
    ompl_planning_pipeline_config = {
            "planning_plugin": "ompl_interface/OMPLPlanner",
            "request_adapters": """default_planner_request_adapters/AddTimeOptimalParameterization 
                                default_planner_request_adapters/FixWorkspaceBounds 
                                default_planner_request_adapters/FixStartStateBounds 
                                default_planner_request_adapters/FixStartStateCollision 
                                default_planner_request_adapters/FixStartStatePathConstraints""",
            "start_state_max_bounds_error": 0.1,
    }

    # # Load OMPL specific planning configuration
    ompl_planning_yaml = load_yaml("h1_moveit_config", "config/ompl_planning.yaml")
    ompl_planning_pipeline_config.update(ompl_planning_yaml)

    # Load cuMotion configuration from its config file
    cumotion_config_file_path = os.path.join(
        get_package_share_directory('isaac_ros_cumotion_moveit'),
        'config',
        'isaac_ros_cumotion_planning.yaml'
    )
    with open(cumotion_config_file_path) as cumotion_config_file:
        cumotion_config = yaml.safe_load(cumotion_config_file)

    planning_pipelines = {}
    # Add both OMPL and cuMotion to the planning pipelines
    planning_pipelines['planning_pipelines'] = ["isaac_ros_cumotion", "ompl"]
    planning_pipelines['default_planning_pipeline'] = "ompl"
    planning_pipelines['isaac_ros_cumotion'] = cumotion_config
    planning_pipelines['ompl'] = ompl_planning_pipeline_config


    # Trajectory Execution Configuration
    controllers_yaml = load_yaml("h1_moveit_config", "config/moveit_controllers.yaml")
    
    moveit_controllers = {
        "moveit_simple_controller_manager": controllers_yaml,
        "moveit_controller_manager": "moveit_simple_controller_manager/MoveItSimpleControllerManager",
        "trajectory_execution" : {
            "allowed_execution_duration_scaling": 2.0,  # change execution time scaling here
            "allowed_goal_duration_margin": 0.5,
            "allowed_start_tolerance": 0.01,
        }
    }

    trajectory_execution = {
        "moveit_manage_controllers": False,
        "trajectory_execution.allowed_execution_duration_scaling": 1.2,
        "trajectory_execution.allowed_goal_duration_margin": 0.5,
        "trajectory_execution.allowed_start_tolerance": 0.01,
    }

    planning_scene_monitor_parameters = {
        "publish_planning_scene": True,
        "publish_geometry_updates": True,
        "publish_state_updates": True,
        "publish_transforms_updates": True,
        "publish_robot_description":True,
        "publish_robot_description_semantic":True,
    }


    # Start the actual move_group node/action server
    move_group_node = Node(
        package="moveit_ros_move_group",
        executable="move_group",
        output="screen",
        parameters=[
            robot_description,
            robot_description_semantic,
            robot_description_kinematics,
            robot_description_planning,
            #octomap_config,
            #octomap_updater_config,
            # ompl_planning_yaml,
            # ompl_planning_pipeline_config,
            planning_pipelines,
            trajectory_execution,
            moveit_controllers,
            planning_scene_monitor_parameters,
            {"use_sim_time": use_sim_time},
        ],
    )

    # rviz with moveit configuration
    rviz_config_file = PathJoinSubstitution(
        [FindPackageShare(moveit_config_package), "config", "moveit.rviz"]
    )
    rviz_node = Node(
        package="rviz2",
        condition=IfCondition(launch_rviz),
        executable="rviz2",
        name="rviz2_moveit",
        output="log",
        arguments=["-d", rviz_config_file],
        parameters=[
            robot_description,
            robot_description_semantic,
            # ompl_planning_pipeline_config,
            planning_pipelines,
            robot_description_kinematics,
            robot_description_planning,
        ],
    )
    node_robot_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        parameters=[robot_description],
        output='screen'
    )


    nodes_to_start = [
        move_group_node, 
        rviz_node, 
        node_robot_state_publisher,
    ]

    return nodes_to_start


def generate_launch_description():
    declared_arguments = []
    # General arguments
    declared_arguments.append(
        DeclareLaunchArgument(
            "description_package",
            default_value="h1_moveit_config",
            description="Description package with robot URDF/XACRO files. Usually the argument \
        is not set, it enables use of a custom description.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "description_file",
            default_value="h1.urdf.xacro",
            description="URDF/XACRO description file with the robot.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "moveit_config_package",
            default_value="h1_moveit_config",
            description="MoveIt config package with robot SRDF/XACRO files. Usually the argument \
        is not set, it enables use of a custom moveit config.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "moveit_config_file",
            default_value="h1_real.srdf.xacro",
            description="MoveIt SRDF/XACRO description file with the robot.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "moveit_joint_limits_file",
            default_value="joint_limits.yaml",
            description="MoveIt joint limits that augment or override the values from the URDF robot_description.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "use_sim_time",
            default_value="false",
            description="Make MoveIt to use simulation time. This is needed for the trajectory planing in simulation.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "prefix",
            default_value='""',
            description="Prefix of the joint names, useful for \
        multi-robot setup. If changed than also joint names in the controllers' configuration \
        have to be updated.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument("launch_rviz", default_value="true", description="Launch RViz?")
    )

    return LaunchDescription(declared_arguments + [OpaqueFunction(function=launch_setup)])
```