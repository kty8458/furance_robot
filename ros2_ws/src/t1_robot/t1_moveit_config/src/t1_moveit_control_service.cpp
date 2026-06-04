#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>
#include "control_interfaces/srv/move_p.hpp"
#include "control_interfaces/srv/move_l.hpp"
#include "control_interfaces/srv/execute_trajectory.hpp"
#include <thread>
#include <chrono>
#include <moveit/move_group_interface/move_group_interface.h>
#include <moveit/planning_scene_interface/planning_scene_interface.h>
#include <moveit/planning_scene_monitor/planning_scene_monitor.h>
#include <moveit/planning_scene/planning_scene.h>
#include <moveit_msgs/msg/display_robot_state.hpp>
#include <moveit_msgs/msg/display_trajectory.hpp>
#include <moveit_msgs/msg/attached_collision_object.hpp>
#include <moveit_msgs/msg/collision_object.hpp>
#include <control_msgs/action/gripper_command.hpp>
#include <tf2/LinearMath/Quaternion.h>
#include <tf2/LinearMath/Matrix3x3.h>
#include <cmath>
#include <tf2_ros/buffer.h>
#include <tf2_ros/transform_listener.h>
#include <moveit/robot_trajectory/robot_trajectory.h>
#include <moveit/trajectory_processing/iterative_time_parameterization.h>
#include <fstream>
#include <string>
#include <ctime>
#include "rmw/qos_profiles.h"
#include "rclcpp_action/rclcpp_action.hpp"
#include "rclcpp_action/server.hpp"
#include <rclcpp/executors/multi_threaded_executor.hpp>

class DualArmRobot : public rclcpp::Node{
public:
    explicit DualArmRobot();
    void init();
    std::vector<double> get_current_angles(
        const std::string & LoR
    );

    bool single_move_p(
        const std::string & LoR,
        geometry_msgs::msg::PoseStamped target_pose,
        const std::string & to_frame,
        const std::string & reference_frame,
        const std::string & planner
        );

    bool move_j(
        const std::string & LoR,
        const std::vector<double>& target_joint_positions);

    bool move_l(
        const std::string & LoR,
        const std::vector<geometry_msgs::msg::Pose>& waypoints
    );



private:
    const std::string LEFT_PLANNING_GROUP = "left_arm";
    const std::string RIGHT_PLANNING_GROUP = "right_arm";
    moveit::planning_interface::MoveGroupInterfacePtr left_move_group_;
    moveit::planning_interface::MoveGroupInterfacePtr right_move_group_;

    moveit::planning_interface::PlanningSceneInterface planning_scene_interface_;

    rclcpp::Service<control_interfaces::srv::ExecuteTrajectory>::SharedPtr execute_trajectory_service_;
    rclcpp::Service<control_interfaces::srv::MoveP>::SharedPtr move_p_service_;
    rclcpp::Service<control_interfaces::srv::MoveL>::SharedPtr move_l_service_;

    std::shared_ptr<tf2_ros::TransformListener> tf_listener_{nullptr};
    std::unique_ptr<tf2_ros::Buffer> tf_buffer_;

    void handle_movep_request(
        const std::shared_ptr<control_interfaces::srv::MoveP::Request> request,
        std::shared_ptr<control_interfaces::srv::MoveP::Response> response
    );
    void handle_movel_request(
        const std::shared_ptr<control_interfaces::srv::MoveL::Request> request,
        std::shared_ptr<control_interfaces::srv::MoveL::Response> response
    );

    void handle_trajectory_request(
    const std::shared_ptr<control_interfaces::srv::ExecuteTrajectory::Request> request,
    std::shared_ptr<control_interfaces::srv::ExecuteTrajectory::Response> response);

    rclcpp::CallbackGroup::SharedPtr callback_group_;
};

DualArmRobot::DualArmRobot()
        : Node("dual_arm_robot"){

    this->callback_group_ = this->create_callback_group(rclcpp::CallbackGroupType::Reentrant);
    auto action_options = rcl_action_server_get_default_options();



    execute_trajectory_service_ = create_service<control_interfaces::srv::ExecuteTrajectory>(
      "execute_trajectory",
      std::bind(&DualArmRobot::handle_trajectory_request, this, std::placeholders::_1, std::placeholders::_2),
      rmw_qos_profile_services_default,
      callback_group_);

    move_p_service_ = create_service<control_interfaces::srv::MoveP>(
    "move_pose",
    std::bind(&DualArmRobot::handle_movep_request, this, std::placeholders::_1, std::placeholders::_2),
    rmw_qos_profile_services_default,
    callback_group_);

    move_l_service_ = create_service<control_interfaces::srv::MoveL>(
    "move_line",
    std::bind(&DualArmRobot::handle_movel_request, this, std::placeholders::_1, std::placeholders::_2),
    rmw_qos_profile_services_default,
    callback_group_);

    tf_buffer_ = std::make_unique<tf2_ros::Buffer>(this->get_clock(), tf2::Duration(std::chrono::seconds(60)));
    tf_listener_ = std::make_shared<tf2_ros::TransformListener>(*tf_buffer_);
    RCLCPP_INFO(this->get_logger(), "Create Tf buffer and listener");
}

void DualArmRobot::init(){
  left_move_group_ = std::make_shared<moveit::planning_interface::MoveGroupInterface>(shared_from_this(), LEFT_PLANNING_GROUP);
  right_move_group_ = std::make_shared<moveit::planning_interface::MoveGroupInterface>(shared_from_this(), RIGHT_PLANNING_GROUP);
}

bool DualArmRobot::single_move_p(
  const std::string & LoR,
  geometry_msgs::msg::PoseStamped target_pose,
  const std::string & to_frame,
  const std::string & reference_frame,
  const std::string & planner
){
  try
  {
    rclcpp::sleep_for(std::chrono::milliseconds(200));
    moveit::planning_interface::MoveGroupInterfacePtr move_group;
    if (LoR == "left"){
      move_group = left_move_group_;
    } else {
      move_group = right_move_group_;
    }

    RCLCPP_INFO(this->get_logger(),"pose is %f, %f, %f.", target_pose.pose.position.x, target_pose.pose.position.y, target_pose.pose.position.z);
    move_group->setPoseReferenceFrame(reference_frame);
    move_group->setEndEffectorLink(to_frame);
    move_group->setPoseTarget(target_pose, to_frame);
    moveit::planning_interface::MoveGroupInterface::Plan my_plan;
    RCLCPP_INFO(this->get_logger(),"Begin plan to target_pose.");
    bool success = (move_group->plan(my_plan)
                    == moveit::core::MoveItErrorCode::SUCCESS);
    if (success){
      RCLCPP_INFO(this->get_logger(),"Move to target_pose successful.");
      move_group->execute(my_plan);
      move_group->clearPathConstraints();
      return true;
    } else {
      RCLCPP_ERROR(this->get_logger(),"Planning failed to target_pose.");
      move_group->clearPathConstraints();
      return false;
    }
  }
  catch(const std::exception& e)
  {
    RCLCPP_INFO(this->get_logger(),"Move P ERROR.");
    return false;
  }
}


bool DualArmRobot::move_l(
  const std::string & LoR,
  const std::vector<geometry_msgs::msg::Pose>& waypoints
){
  rclcpp::sleep_for(std::chrono::milliseconds(200));
  RCLCPP_INFO(this->get_logger(), "Received Goal: lor = %s", LoR.c_str());
  moveit::planning_interface::MoveGroupInterfacePtr move_group;
  if (LoR == "left"){
    move_group = left_move_group_;
  }
  if (LoR == "right") {
    move_group = right_move_group_;
  }

  if (!move_group) {
    RCLCPP_ERROR(this->get_logger(), "Move group is not initialized properly.");
    return false;
  }
  // t1 uses SJ_Link as the shoulder base (no waist_Link)
  move_group->setPoseReferenceFrame("base_link");
  if(waypoints.empty()) {
      RCLCPP_ERROR(this->get_logger(), "Waypoints list is empty");
      return false;
  }

  try {
      move_group->setStartStateToCurrentState();
      constexpr int MAX_RETRIES = 5;
      constexpr double INITIAL_EEF_STEP = 0.01;
      constexpr double STEP_DECAY_FACTOR = 0.5;
      double current_eef_step = INITIAL_EEF_STEP;
      double jump_threshold = 0.01;
      double max_vel_scaling = 0.25;
      double max_accel_scaling = 0.25;
      bool success = false;
      int attempt = 0;
      moveit_msgs::msg::RobotTrajectory trajectory_msg;
      do {

          double fraction = move_group->computeCartesianPath(
              waypoints,
              current_eef_step,
              jump_threshold,
              trajectory_msg,
              true,
              nullptr
          );

          if(fraction >= 0.85) {
              success = true;
              break;
          } else {
              current_eef_step *= STEP_DECAY_FACTOR;
              RCLCPP_WARN(get_logger(), "Attempt %d failed (%.1f%%), retrying with eef_step=%.3f",
                        attempt+1, fraction*100, current_eef_step);
          }
      } while (++attempt < MAX_RETRIES);
      if(success == false){
        RCLCPP_ERROR(this->get_logger(), "compute failed");
        return false;
      }

      robot_trajectory::RobotTrajectory trajectory(
          move_group->getCurrentState()->getRobotModel(),
          move_group->getName()
      );
      trajectory.setRobotTrajectoryMsg(*move_group->getCurrentState(), trajectory_msg);

      trajectory_processing::IterativeParabolicTimeParameterization time_param;
      if(!time_param.computeTimeStamps(trajectory, max_vel_scaling, max_accel_scaling)) {
          RCLCPP_ERROR(this->get_logger(), "Time parameterization failed");
          return false;
      }


      moveit::planning_interface::MoveGroupInterface::Plan plan;
      plan.trajectory_ = trajectory_msg;

      if(move_group->execute(plan) == moveit::core::MoveItErrorCode::SUCCESS) {
          return true;
      } else {
          RCLCPP_ERROR(this->get_logger(), "Execute failed");
          return false;
      }

  } catch (const std::exception& e) {
      RCLCPP_ERROR(this->get_logger(), e.what());
      return false;
  }
}



void DualArmRobot::handle_trajectory_request(
    const std::shared_ptr<control_interfaces::srv::ExecuteTrajectory::Request> request,
    std::shared_ptr<control_interfaces::srv::ExecuteTrajectory::Response> response
){
    RCLCPP_INFO(rclcpp::get_logger("execute_trajectory_server"), "Received trajectory");
    const std::string& first_joint = request->trajectory.joint_names[0];
    moveit::planning_interface::MoveGroupInterfacePtr move_group;
    std::vector<double> first_target = request->trajectory.points.front().positions;
    if (first_joint.find("ARM-L") != std::string::npos) {
    move_group = left_move_group_;
    RCLCPP_INFO(rclcpp::get_logger("execute_trajectory_server"), "Selected LEFT arm group.");
    } else if (first_joint.find("ARM-R") != std::string::npos) {
    move_group = right_move_group_;
    RCLCPP_INFO(rclcpp::get_logger("execute_trajectory_server"), "Selected RIGHT arm group.");
    }
    robot_trajectory::RobotTrajectory robot_traj(move_group->getRobotModel(), move_group->getName());

    moveit::core::RobotState start_state = *move_group->getCurrentState();

    const auto& joint_names = request->trajectory.joint_names;
    const auto& traj_points = request->trajectory.points;

    for (const auto& pt : traj_points) {
        moveit::core::RobotState state(start_state);
        state.setVariablePositions(joint_names, pt.positions);
        state.update();
        robot_traj.addSuffixWayPoint(state, pt.time_from_start.sec + pt.time_from_start.nanosec * 1e-9);
    }

    moveit::planning_interface::MoveGroupInterface::Plan plan;
    moveit_msgs::msg::RobotTrajectory trajectory_msg;
    robot_traj.getRobotTrajectoryMsg(trajectory_msg);
    plan.trajectory_ = trajectory_msg;

    moveit::core::MoveItErrorCode result = move_group->execute(plan);
    if (result == moveit::core::MoveItErrorCode::SUCCESS) {
        response->success = true;
        response->message = "Trajectory executed successfully via MoveIt.";
        RCLCPP_INFO(rclcpp::get_logger("execute_trajectory_server"), "Execution succeeded.");
    } else {
        response->success = false;
        response->message = "Execution failed (code=" + std::to_string(result.val) + ").";
        RCLCPP_ERROR(rclcpp::get_logger("execute_trajectory_server"),
                     "Execution failed with MoveItErrorCode=%d", result.val);
    }
}

void DualArmRobot::handle_movep_request(
    const std::shared_ptr<control_interfaces::srv::MoveP::Request> request,
    std::shared_ptr<control_interfaces::srv::MoveP::Response> response
){
    RCLCPP_INFO(rclcpp::get_logger("move_p_server"), "Received movep");
    try{
        bool success = single_move_p(request->lor, request->target_pose, request->to_frame, request->reference_frame, request->planner);
        if (success == true) {
            response->success = true;
            response->message = "MoveP success.";
            RCLCPP_INFO(rclcpp::get_logger("move_p_server"), "Execution succeeded.");
        } else {
            response->success = false;
            response->message = "MoveP failed.";
            RCLCPP_ERROR(rclcpp::get_logger("move_p_server"), "Execution failed.");
        }
    }
    catch(const std::exception& e)
    {
        RCLCPP_ERROR(rclcpp::get_logger("move_p_server"), "Execution failed.");
    }
}

void DualArmRobot::handle_movel_request(
    const std::shared_ptr<control_interfaces::srv::MoveL::Request> request,
    std::shared_ptr<control_interfaces::srv::MoveL::Response> response
){
    RCLCPP_INFO(rclcpp::get_logger("move_l_server"), "Received moveL");
    try{
        bool success = move_l(request->lor, request->waypoints);
        if (success == true) {
            response->success = true;
            response->message = "MoveL success.";
            RCLCPP_INFO(rclcpp::get_logger("move_p_server"), "Execution succeeded.");
        } else {
            response->success = false;
            response->message = "MoveL failed.";
            RCLCPP_ERROR(rclcpp::get_logger("move_p_server"), "Execution failed.");
        }
    }
    catch(const std::exception& e)
    {
        RCLCPP_ERROR(rclcpp::get_logger("move_p_server"), "Execution failed.");
    }
}

int main(int argc, char **argv)
{
  rclcpp::init(argc, argv);
  auto node = std::make_shared<DualArmRobot>();
  node->init();
  rclcpp::executors::MultiThreadedExecutor executor(rclcpp::ExecutorOptions(), 4);
  executor.add_node(node);
  executor.spin();
  rclcpp::shutdown();
  return 0;
}
