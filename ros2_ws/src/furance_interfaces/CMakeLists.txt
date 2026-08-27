cmake_minimum_required(VERSION 3.8)
project(furance_interfaces)

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "srv/GenericCommand.srv"
)

# Post-install: copy entire install output to robot_control backend
# 注意: 必须用 install(CODE) 而不是 add_custom_target(ALL):
#   1. custom_target(ALL) 跑在 gmake 阶段, 首次构建时 install/furance_interfaces
#      尚未由 cmake install 步骤填充, 源目录不存在 -> "Error copying directory"
#      (报错后重跑成功是侥幸, 依赖并行时序)
#   2. cmake -E copy_directory 不会自动创建目标目录, ros2_libs 被 gitignore,
#      新 clone 后不存在, 必须先 make_directory
# install(CODE) 保证拷贝发生在 colcon install 步骤内, 源目录必已完整
install(CODE "
  set(BACKEND_DIR \"${CMAKE_CURRENT_SOURCE_DIR}/../../../robot_control/backend/ros2_libs\")
  set(INSTALL_DIR \"${CMAKE_CURRENT_SOURCE_DIR}/../../install/furance_interfaces\")
  message(STATUS \"Copying furance_interfaces install to robot_control backend\")
  file(MAKE_DIRECTORY \"\${BACKEND_DIR}\")
  file(REMOVE_RECURSE \"\${BACKEND_DIR}\")
  file(COPY \"\${INSTALL_DIR}/\" DESTINATION \"\${BACKEND_DIR}\")
")

ament_package()
