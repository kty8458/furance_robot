cmake_minimum_required(VERSION 3.8)
project(grippers_control)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(std_msgs REQUIRED)
find_package(control_interfaces REQUIRED)

# SOEM install prefix. Override with the SOEM_ROOT environment variable;
# falls back to the sibling ../SOEM/install location used by gripper_test.
set(SOEM_ROOT "$ENV{SOEM_ROOT}" CACHE PATH "SOEM install prefix")
if(NOT SOEM_ROOT)
  set(SOEM_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../SOEM/install")
endif()
set(SOEM_INCLUDE_DIR "${SOEM_ROOT}/include")
set(SOEM_LIBRARY "${SOEM_ROOT}/lib/libsoem.a")

if(NOT EXISTS "${SOEM_LIBRARY}")
  message(FATAL_ERROR "SOEM static library not found: ${SOEM_LIBRARY}. Please build and install SOEM (set SOEM_ROOT to its install prefix).")
endif()

# ROS2 service/status node driving the EtherCAT grippers via SOEM.
add_executable(gripper_node src/gripper_node.cpp)
target_include_directories(gripper_node SYSTEM PRIVATE
  "${SOEM_INCLUDE_DIR}"
  "${SOEM_INCLUDE_DIR}/soem"
)
target_link_libraries(gripper_node "${SOEM_LIBRARY}" m)
ament_target_dependencies(gripper_node rclcpp std_msgs control_interfaces)

# Standalone C utilities (raw SOEM/EtherCAT, no ROS2 dependency).
add_executable(gripper_control src/gripper_control.c)
target_include_directories(gripper_control SYSTEM PRIVATE "${SOEM_INCLUDE_DIR}" "${SOEM_INCLUDE_DIR}/soem")
target_link_libraries(gripper_control "${SOEM_LIBRARY}" m)

add_executable(read_gripper_sdo src/read_gripper_sdo.c)
target_include_directories(read_gripper_sdo SYSTEM PRIVATE "${SOEM_INCLUDE_DIR}" "${SOEM_INCLUDE_DIR}/soem")
target_link_libraries(read_gripper_sdo "${SOEM_LIBRARY}" m)

install(TARGETS gripper_node gripper_control read_gripper_sdo
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY config launch
  DESTINATION share/${PROJECT_NAME}
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  set(ament_cmake_copyright_FOUND TRUE)
  set(ament_cmake_cpplint_FOUND TRUE)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
