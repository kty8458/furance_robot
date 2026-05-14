cmake_minimum_required(VERSION 3.22)
project(t1_moveit_config)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(moveit_common REQUIRED)
find_package(moveit_core REQUIRED)
find_package(moveit_ros_planning_interface REQUIRED)
find_package(moveit_ros_planning REQUIRED)
find_package(rclcpp_components REQUIRED)
find_package(rclcpp_action REQUIRED)
find_package(control_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(control_interfaces REQUIRED)
find_package(rmw REQUIRED)

install(DIRECTORY launch DESTINATION share/${PROJECT_NAME}
  PATTERN "setup_assistant.launch" EXCLUDE)
install(DIRECTORY config DESTINATION share/${PROJECT_NAME})
install(FILES .setup_assistant DESTINATION share/${PROJECT_NAME})

add_executable(t1_moveit_server src/t1_moveit_control_service.cpp)
ament_target_dependencies(t1_moveit_server
rclcpp moveit_ros_planning_interface tf2
moveit_core moveit_ros_planning control_msgs  control_interfaces rmw)

install(TARGETS t1_moveit_server
  DESTINATION lib/${PROJECT_NAME}
)

ament_package()
