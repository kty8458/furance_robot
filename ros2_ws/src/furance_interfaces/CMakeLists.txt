cmake_minimum_required(VERSION 3.8)
project(furance_interfaces)

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "srv/GenericCommand.srv"
)

# Post-install: copy entire install output to robot_control backend
set(BACKEND_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../../robot_control/backend/ros2_libs")
set(INSTALL_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../install/furance_interfaces")
add_custom_target(copy_to_backend ALL
  COMMAND ${CMAKE_COMMAND} -E remove_directory ${BACKEND_DIR}
  COMMAND ${CMAKE_COMMAND} -E copy_directory ${INSTALL_DIR} ${BACKEND_DIR}
  COMMENT "Copying furance_interfaces install to robot_control backend"
  VERBATIM
)
add_dependencies(copy_to_backend ${PROJECT_NAME})

ament_package()
