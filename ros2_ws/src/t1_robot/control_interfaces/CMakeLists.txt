cmake_minimum_required(VERSION 3.8)
project(control_interfaces)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# find dependencies
find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(rosidl_generator_dds_idl REQUIRED)
find_package(action_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(trajectory_msgs REQUIRED)
set(
  DEPENDENCY_LIST
  action_msgs 
  geometry_msgs
  sensor_msgs
  trajectory_msgs
)
rosidl_generate_interfaces(${PROJECT_NAME}
  "srv/YoloDetection.srv"
  "srv/GetImage.srv"
  "srv/StartNode.srv" 
  "srv/StopNode.srv" 
  "srv/QRDetection.srv"
  "srv/ManageObstacle.srv"
  "srv/TeleopCommand.srv"
  "srv/ComputeIk.srv"
  "srv/ExecuteTrajectory.srv"
  "srv/GetJoint.srv"
  "srv/GetPose.srv"
  "srv/MoveP.srv"
  "srv/MoveL.srv"
  "action/GripperAction.action" 
  "action/MoveP.action"
  "action/MoveJ.action"
  "action/MoveL.action"
  "action/HandAction.action"
  "action/UpperAction.action"
  "action/Navigation.action"
  DEPENDENCIES  ${DEPENDENCY_LIST}
)

ament_package()
