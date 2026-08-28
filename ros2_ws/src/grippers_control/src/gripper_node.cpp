#include <soem/ethercat.h>

#include <algorithm>
#include <cctype>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <memory>
#include <mutex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

#include "control_interfaces/msg/ec_grippers_status.hpp"
#include "control_interfaces/srv/ec_grippers_control.hpp"
#include "rclcpp/rclcpp.hpp"

namespace
{

constexpr uint16_t kNeutralCommand = 0x0080;
constexpr uint16_t kOpenCommand = 0x0081;
constexpr uint16_t kCloseCommand = 0x0082;
// 说明书第9章 RXPDO Comand: bit7=参数同步(常规置1), bit0~1=3 为清除故障指令
constexpr uint16_t kClearFaultCommand = 0x0083;

#pragma pack(push, 1)

struct GripperRxPDO
{
  uint16 command;
  uint16 enable;
  uint16 close_speed;
  uint16 open_speed;
  uint16 close_force;
  uint16 close_width;
  uint16 open_width;
  uint16 object_width;
  uint16 object_width_error;
  uint16 max_finger_width;
  uint16 min_finger_width;
  uint16 reserved[9];
};

struct GripperTxPDO
{
  uint16 io_status;
  uint16 claw_status;
  uint16 claw_error;
  uint16 motor_status;
  uint16 motor_error;
  uint16 current_finger_width;
  uint16 current_position;
  uint16 target_position;
  uint16 target_current;
  uint16 bus_voltage;
  uint16 driver_temperature;
  uint16 reserved[9];
};

#pragma pack(pop)

static_assert(sizeof(GripperRxPDO) == 40, "RxPDO size must be 40 bytes");
static_assert(sizeof(GripperTxPDO) == 40, "TxPDO size must be 40 bytes");

struct GripperConfig
{
  std::string name;
  int slave_index = 0;
  uint16_t enable = 1;
  uint16_t close_speed = 80;
  uint16_t open_speed = 80;
  uint16_t close_force = 200;
  uint16_t close_width = 1000;
  uint16_t open_width = 1800;
  uint16_t object_width = 0;
  uint16_t object_width_error = 0;
  uint16_t max_finger_width = 1820;
  uint16_t min_finger_width = 0;
};

struct GripperRuntime
{
  GripperConfig config;
  GripperRxPDO * rx = nullptr;
  GripperTxPDO * tx = nullptr;
};

const char * claw_status_text(uint16_t status)
{
  switch (status) {
    case 0:
      return "not initialized";
    case 1:
      return "waiting for homing";
    case 2:
      return "homing";
    case 3:
      return "ready";
    case 4:
      return "opening";
    case 5:
      return "open position reached";
    case 6:
      return "closing";
    case 7:
      return "grip successful";
    case 8:
      return "empty grip";
    case 9:
      return "object dropped";
    case 10:
      return "fault";
    default:
      return "unknown";
  }
}

bool is_ready_status(uint16_t status)
{
  return status == 3 || status == 5 || status == 7 || status == 8;
}

double units_to_mm(uint16_t units)
{
  return static_cast<double>(units) / 10.0;
}

}  // namespace

class GripperNode : public rclcpp::Node
{
public:
  GripperNode()
  : Node("gripper_node")
  {
    interface_name_ = declare_parameter<std::string>("interface_name", "");
    expected_device_name_ = declare_parameter<std::string>("expected_device_name", "EPG-L80-400");
    cycle_us_ = declare_positive_int("cycle_us", 5000);
    ready_timeout_cycles_ = declare_positive_int("ready_timeout_cycles", 4000);
    move_timeout_cycles_ = declare_positive_int("move_timeout_cycles", 6000);
    position_tolerance_units_ = declare_positive_int("position_tolerance_units", 3);
    monitor_period_ms_ = declare_positive_int("monitor_period_ms", 100);

    const auto gripper_names =
      declare_parameter<std::vector<std::string>>("grippers", {"right", "left"});
    for (const auto & name : gripper_names) {
      grippers_.push_back(load_gripper_config(name));
    }

    status_pub_ = create_publisher<control_interfaces::msg::ECGrippersStatus>(
      "~/EC_grippers_status", 10);
    control_srv_ = create_service<control_interfaces::srv::ECGrippersControl>(
      "~/EC_grippers_control",
      std::bind(&GripperNode::handle_control, this, std::placeholders::_1, std::placeholders::_2));

    if (!initialize_ethercat()) {
      RCLCPP_ERROR(
        get_logger(),
        "EtherCAT initialization failed. Check interface_name, sudo/capabilities, cabling, and slave indices.");
    }

    cycle_timer_ = create_wall_timer(
      std::chrono::microseconds(cycle_us_),
      std::bind(&GripperNode::ethercat_cycle_once, this));

    status_timer_ = create_wall_timer(
      std::chrono::milliseconds(monitor_period_ms_),
      std::bind(&GripperNode::publish_all_status, this));
  }

  ~GripperNode() override
  {
    std::lock_guard<std::mutex> lock(ethercat_mutex_);

    if (!operational_) {
      return;
    }

    for (auto & gripper : grippers_) {
      if (gripper.rx != nullptr) {
        gripper.rx->command = kNeutralCommand;
      }
    }

    for (int i = 0; i < 20; ++i) {
      exchange_once_locked();
      std::this_thread::sleep_for(std::chrono::microseconds(cycle_us_));
    }

    ec_slave[0].state = EC_STATE_INIT;
    ec_writestate(0);
    ec_close();
    operational_ = false;
  }

private:
  int declare_positive_int(const std::string & name, int default_value)
  {
    const int value = declare_parameter<int>(name, default_value);
    if (value <= 0) {
      throw std::runtime_error(name + " must be positive");
    }
    return value;
  }

  uint16_t declare_u16(
    const std::string & name,
    int default_value,
    int min_value = 0,
    int max_value = 65535)
  {
    const int value = declare_parameter<int>(name, default_value);
    if (value < min_value || value > max_value) {
      std::ostringstream error;
      error << name << " must be in [" << min_value << ", " << max_value << "]";
      throw std::runtime_error(error.str());
    }
    return static_cast<uint16_t>(value);
  }

  GripperRuntime load_gripper_config(const std::string & name)
  {
    GripperRuntime runtime;
    runtime.config.name = name;
    runtime.config.slave_index = declare_parameter<int>(name + ".slave_index", 0);
    runtime.config.enable = declare_u16(name + ".enable", 1, 0, 1);
    runtime.config.close_speed = declare_u16(name + ".close_speed", 80, 1, 255);
    runtime.config.open_speed = declare_u16(name + ".open_speed", 80, 1, 255);
    runtime.config.close_force = declare_u16(name + ".close_force", 200);
    runtime.config.close_width = declare_u16(name + ".close_width_units", 1000);
    runtime.config.open_width = declare_u16(name + ".open_width_units", 1800);
    runtime.config.object_width = declare_u16(name + ".object_width_units", 0);
    runtime.config.object_width_error = declare_u16(name + ".object_width_error_units", 0);
    runtime.config.max_finger_width = declare_u16(name + ".max_finger_width_units", 1800);
    runtime.config.min_finger_width = declare_u16(name + ".min_finger_width_units", 1000);

    if (runtime.config.slave_index <= 0) {
      throw std::runtime_error(name + ".slave_index must be positive");
    }
    if (runtime.config.min_finger_width > runtime.config.max_finger_width) {
      throw std::runtime_error(name + " min_finger_width_units exceeds max_finger_width_units");
    }
    if (runtime.config.close_width < runtime.config.min_finger_width ||
      runtime.config.close_width > runtime.config.max_finger_width)
    {
      throw std::runtime_error(name + " close_width_units is outside configured finger range");
    }
    if (runtime.config.open_width < runtime.config.min_finger_width ||
      runtime.config.open_width > runtime.config.max_finger_width)
    {
      throw std::runtime_error(name + " open_width_units is outside configured finger range");
    }

    return runtime;
  }

  bool initialize_ethercat()
  {
    std::lock_guard<std::mutex> lock(ethercat_mutex_);

    if (interface_name_.empty()) {
      RCLCPP_ERROR(get_logger(), "Parameter interface_name is empty.");
      return false;
    }

    if (!ec_init(interface_name_.c_str())) {
      RCLCPP_ERROR(get_logger(), "Failed to open interface %s.", interface_name_.c_str());
      return false;
    }

    if (ec_config_init(FALSE) <= 0) {
      RCLCPP_ERROR(get_logger(), "No EtherCAT slaves found.");
      ec_close();
      return false;
    }

    ec_config_map(io_map_);
    ec_configdc();
    ec_statecheck(0, EC_STATE_SAFE_OP, EC_TIMEOUTSTATE * 4);

    RCLCPP_INFO(get_logger(), "%d EtherCAT slave(s) found.", ec_slavecount);

    // 鲁棒性: 扫描所有 slave, 按设备名(EPG-L80-400)过滤出夹爪 slave,
    // 再按 right->left 顺序绑定 (支持 EtherCAT 分线器等非夹爪 slave 混在总线上)
    std::vector<int> gripper_slave_indices;
    for (int s = 1; s <= ec_slavecount; ++s) {
      const char * sname = ec_slave[s].name;
      if (expected_device_name_.empty() || expected_device_name_ == sname) {
        gripper_slave_indices.push_back(s);
        RCLCPP_INFO(get_logger(), "Slave %d = %s (gripper)", s, sname);
      } else {
        RCLCPP_INFO(get_logger(), "Slave %d = %s (non-gripper, skip)", s, sname);
      }
    }

    if (gripper_slave_indices.empty()) {
      RCLCPP_WARN(get_logger(), "No gripper slaves (expected %s) found; node will run idle.",
                  expected_device_name_.c_str());
      grippers_.clear();
    } else {
      // 按顺序把夹爪 slave 分配给配置的 grippers (right->left)
      std::vector<GripperRuntime> mapped;
      for (size_t i = 0; i < grippers_.size() && i < gripper_slave_indices.size(); ++i) {
        GripperRuntime g = grippers_[i];
        const int new_slave = gripper_slave_indices[i];
        if (g.config.slave_index != new_slave) {
          RCLCPP_INFO(get_logger(),
                      "Gripper %s: remap slave_index %d -> %d.",
                      g.config.name.c_str(), g.config.slave_index, new_slave);
          g.config.slave_index = new_slave;
        }
        mapped.push_back(g);
      }
      if (grippers_.size() > gripper_slave_indices.size()) {
        RCLCPP_WARN(get_logger(),
                    "%zu gripper(s) connected, %zu configured; using first %zu.",
                    gripper_slave_indices.size(), grippers_.size(), gripper_slave_indices.size());
      }
      grippers_.swap(mapped);
    }

    for (auto & gripper : grippers_) {
      if (!bind_gripper_locked(gripper)) {
        ec_close();
        return false;
      }
    }

    expected_wkc_ = (ec_group[0].outputsWKC * 2) + ec_group[0].inputsWKC;
    exchange_once_locked();

    ec_slave[0].state = EC_STATE_OPERATIONAL;
    ec_writestate(0);

    int retries = 200;
    do {
      exchange_once_locked();
      ec_statecheck(0, EC_STATE_OPERATIONAL, 50000);
    } while (retries-- > 0 && ec_slave[0].state != EC_STATE_OPERATIONAL);

    if (ec_slave[0].state != EC_STATE_OPERATIONAL) {
      RCLCPP_ERROR(get_logger(), "Failed to reach EtherCAT OPERATIONAL state.");
      ec_close();
      return false;
    }

    operational_ = true;
    last_wkc_ = exchange_once_locked();
    RCLCPP_INFO(get_logger(), "EtherCAT OPERATIONAL state reached.");

    for (auto & gripper : grippers_) {
      std::string message;
      if (!wait_until_ready_locked(gripper, &message)) {
        RCLCPP_WARN(
          get_logger(),
          "Gripper %s is not ready after initialization yet: %s",
          gripper.config.name.c_str(),
          message.c_str());
      }
    }

    return true;
  }

  bool bind_gripper_locked(GripperRuntime & gripper)
  {
    const int slave = gripper.config.slave_index;
    if (slave < 1 || slave > ec_slavecount) {
      RCLCPP_ERROR(
        get_logger(),
        "Invalid slave index %d for gripper %s; current slave count is %d.",
        slave,
        gripper.config.name.c_str(),
        ec_slavecount);
      return false;
    }

    if (!expected_device_name_.empty() && expected_device_name_ != ec_slave[slave].name) {
      RCLCPP_ERROR(
        get_logger(),
        "Slave %d for gripper %s is %s, expected %s.",
        slave,
        gripper.config.name.c_str(),
        ec_slave[slave].name,
        expected_device_name_.c_str());
      return false;
    }

    if (ec_slave[slave].Obytes < static_cast<int>(sizeof(GripperRxPDO)) ||
      ec_slave[slave].Ibytes < static_cast<int>(sizeof(GripperTxPDO)))
    {
      RCLCPP_ERROR(
        get_logger(),
        "Unexpected PDO size on gripper %s: output=%d input=%d.",
        gripper.config.name.c_str(),
        ec_slave[slave].Obytes,
        ec_slave[slave].Ibytes);
      return false;
    }

    gripper.rx = reinterpret_cast<GripperRxPDO *>(ec_slave[slave].outputs);
    gripper.tx = reinterpret_cast<GripperTxPDO *>(ec_slave[slave].inputs);

    std::memset(gripper.rx, 0, sizeof(*gripper.rx));
    apply_config_locked(gripper);

    RCLCPP_INFO(
      get_logger(),
      "Bound gripper %s to slave %d (%s).",
      gripper.config.name.c_str(),
      slave,
      ec_slave[slave].name);
    return true;
  }

  void apply_config_locked(GripperRuntime & gripper)
  {
    auto * rx = gripper.rx;
    const auto & config = gripper.config;

    rx->command = kNeutralCommand;
    rx->enable = config.enable;
    rx->close_speed = config.close_speed;
    rx->open_speed = config.open_speed;
    rx->close_force = config.close_force;
    rx->close_width = config.close_width;
    rx->open_width = config.open_width;
    rx->object_width = config.object_width;
    rx->object_width_error = config.object_width_error;
    rx->max_finger_width = config.max_finger_width;
    rx->min_finger_width = config.min_finger_width;
  }

  int exchange_once_locked()
  {
    ec_send_processdata();
    const int wkc = ec_receive_processdata(EC_TIMEOUTRET);

    if (expected_wkc_ > 0 && wkc < expected_wkc_) {
      RCLCPP_WARN_THROTTLE(
        get_logger(),
        *get_clock(),
        2000,
        "Working counter is %d, expected %d.",
        wkc,
        expected_wkc_);
    }

    return wkc;
  }

  bool has_fault_locked(const GripperRuntime & gripper, std::string * message) const
  {
    if (gripper.tx->claw_status == 10 || gripper.tx->claw_error != 0 || gripper.tx->motor_error != 0) {
      std::ostringstream error;
      error << "fault: claw_status=" << gripper.tx->claw_status
            << " (" << claw_status_text(gripper.tx->claw_status) << ")"
            << ", claw_error=0x" << std::hex << gripper.tx->claw_error
            << ", motor_error=0x" << gripper.tx->motor_error;
      *message = error.str();
      return true;
    }
    return false;
  }

  bool wait_until_ready_locked(GripperRuntime & gripper, std::string * message)
  {
    for (int cycle = 0; cycle < ready_timeout_cycles_; ++cycle) {
      const int wkc = exchange_once_locked();

      if ((cycle % 20) == 0) {
        publish_status_locked(gripper, wkc);
      }

      if (has_fault_locked(gripper, message)) {
        return false;
      }

      if (is_ready_status(gripper.tx->claw_status)) {
        *message = "ready";
        return true;
      }

      std::this_thread::sleep_for(std::chrono::microseconds(cycle_us_));
    }

    *message = "timed out waiting for ready state";
    return false;
  }

  void neutralize_locked(GripperRuntime & gripper)
  {
    gripper.rx->command = kNeutralCommand;
    for (int cycle = 0; cycle < 20; ++cycle) {
      exchange_once_locked();
      std::this_thread::sleep_for(std::chrono::microseconds(cycle_us_));
    }
  }

  // 清除故障 (说明书第9章: Comand bit0~1=3 清除故障, 设备尝试恢复正常,
  // 故障仍存在则再次进入故障状态; 解除急停后也需清除故障)
  bool clear_fault_locked(GripperRuntime & gripper, std::string * message)
  {
    gripper.rx->command = kClearFaultCommand;
    for (int cycle = 0; cycle < 20; ++cycle) {
      exchange_once_locked();
      std::this_thread::sleep_for(std::chrono::microseconds(cycle_us_));
    }
    gripper.rx->command = kNeutralCommand;

    for (int cycle = 0; cycle < ready_timeout_cycles_; ++cycle) {
      const int wkc = exchange_once_locked();

      if ((cycle % 20) == 0) {
        publish_status_locked(gripper, wkc);
      }

      if (!has_fault_locked(gripper, message)) {
        *message = "fault cleared";
        return true;
      }

      std::this_thread::sleep_for(std::chrono::microseconds(cycle_us_));
    }

    *message = "fault persists after clear: " + *message;
    return false;
  }

  void ethercat_cycle_once()
  {
    std::lock_guard<std::mutex> lock(ethercat_mutex_);

    if (!operational_) {
      return;
    }

    last_wkc_ = exchange_once_locked();
  }

  void publish_all_status()
  {
    std::lock_guard<std::mutex> lock(ethercat_mutex_);

    if (!operational_) {
      return;
    }

    for (const auto & gripper : grippers_) {
      publish_status_locked(gripper, last_wkc_);
    }
  }

  void handle_control(
    const std::shared_ptr<control_interfaces::srv::ECGrippersControl::Request> request,
    std::shared_ptr<control_interfaces::srv::ECGrippersControl::Response> response)
  {
    std::lock_guard<std::mutex> lock(ethercat_mutex_);

    if (!operational_) {
      response->success = false;
      response->message = "EtherCAT is not operational";
      return;
    }

    auto * gripper = find_gripper_locked(request->gripper_name);
    if (gripper == nullptr) {
      response->success = false;
      response->message = "Unknown gripper: " + request->gripper_name;
      return;
    }

    const std::string command = normalized_command(request->command);
    if (command == "status") {
      const int wkc = exchange_once_locked();
      publish_status_locked(*gripper, wkc);
      fill_response_from_state(*gripper, true, "status updated", response);
      return;
    }

    // 手动清错: 发送清除故障指令并等待故障位消失, 成功后再等待就绪
    if (command == "clear_error" || command == "clear_fault" || command == "clear") {
      std::string clear_message;
      const bool cleared = clear_fault_locked(*gripper, &clear_message);
      if (cleared) {
        std::string ready_message;
        wait_until_ready_locked(*gripper, &ready_message);
        clear_message += ", " + ready_message;
      } else {
        neutralize_locked(*gripper);
      }
      fill_response_from_state(*gripper, cleared, clear_message, response);
      return;
    }

    // open/close/move 前自动清错 (含急停解除后需清错的场景), 无故障时为空操作
    {
      std::string clear_message;
      if (!clear_fault_locked(*gripper, &clear_message)) {
        neutralize_locked(*gripper);
        fill_response_from_state(*gripper, false, clear_message, response);
        return;
      }
    }

    std::string message;
    if (!wait_until_ready_locked(*gripper, &message)) {
      neutralize_locked(*gripper);
      fill_response_from_state(*gripper, false, message, response);
      return;
    }

    uint16_t target_width = 0;
    if (!resolve_target_width(*gripper, command, request->width_mm, &target_width, &message)) {
      fill_response_from_state(*gripper, false, message, response);
      return;
    }

    const bool success = move_to_width_locked(*gripper, target_width, &message);
    fill_response_from_state(*gripper, success, message, response);
  }

  std::string normalized_command(const std::string & command) const
  {
    std::string normalized = command;
    std::transform(normalized.begin(), normalized.end(), normalized.begin(), [](unsigned char c) {
      return static_cast<char>(std::tolower(c));
    });
    return normalized;
  }

  GripperRuntime * find_gripper_locked(const std::string & name)
  {
    for (auto & gripper : grippers_) {
      if (gripper.config.name == name) {
        return &gripper;
      }
    }
    return nullptr;
  }

  bool resolve_target_width(
    const GripperRuntime & gripper,
    const std::string & command,
    double requested_width_mm,
    uint16_t * target_width,
    std::string * message) const
  {
    const auto & config = gripper.config;

    if (command == "open") {
      *target_width = config.open_width;
      return true;
    }

    if (command == "close") {
      *target_width = config.close_width;
      return true;
    }

    if (command != "move") {
      *message = "Unknown command: " + command + ". Use open, close, move, status, or clear_error.";
      return false;
    }

    const auto units = static_cast<int>(std::llround(requested_width_mm * 10.0));
    if (units < config.min_finger_width || units > config.max_finger_width) {
      std::ostringstream error;
      error << "width_mm must be between " << units_to_mm(config.min_finger_width)
            << " and " << units_to_mm(config.max_finger_width) << " mm";
      *message = error.str();
      return false;
    }

    *target_width = static_cast<uint16_t>(units);
    return true;
  }

  bool move_to_width_locked(GripperRuntime & gripper, uint16_t target_width, std::string * message)
  {
    const uint16_t current_width = gripper.tx->current_finger_width;

    if (target_width > current_width) {
      gripper.rx->open_width = target_width;
      gripper.rx->command = kNeutralCommand;
      pulse_neutral_locked();
      gripper.rx->command = kOpenCommand;
      *message = "opening";
    } else if (target_width < current_width) {
      gripper.rx->close_width = target_width;
      gripper.rx->command = kNeutralCommand;
      pulse_neutral_locked();
      gripper.rx->command = kCloseCommand;
      *message = "closing";
    } else {
      *message = "already at target width";
      return true;
    }

    for (int cycle = 0; cycle < 20; ++cycle) {
      exchange_once_locked();
      std::this_thread::sleep_for(std::chrono::microseconds(cycle_us_));
    }

    gripper.rx->command = kNeutralCommand;

    for (int cycle = 0; cycle < move_timeout_cycles_; ++cycle) {
      const int wkc = exchange_once_locked();

      if ((cycle % 20) == 0) {
        publish_status_locked(gripper, wkc);
      }

      if (has_fault_locked(gripper, message)) {
        neutralize_locked(gripper);
        return false;
      }

      // claw=7(grip successful) / 8(empty grip) / 9(object dropped):
      // 夹爪动作终止状态, 无论是否到目标宽度都算完成 (避免空夹时卡死等 width=0)
      const uint16_t cs = gripper.tx->claw_status;
      if (cs == 7 || cs == 8 || cs == 9) {
        std::ostringstream ok;
        ok << "gripper action finished: claw=" << cs
           << " (" << claw_status_text(cs) << "), actual "
           << units_to_mm(gripper.tx->current_finger_width) << " mm";
        *message = ok.str();
        publish_status_locked(gripper, wkc);
        return true;
      }

      const int error = std::abs(
        static_cast<int>(gripper.tx->current_finger_width) - static_cast<int>(target_width));
      if (error <= position_tolerance_units_) {
        std::ostringstream ok;
        ok << "target reached: requested " << units_to_mm(target_width)
           << " mm, actual " << units_to_mm(gripper.tx->current_finger_width) << " mm";
        *message = ok.str();
        publish_status_locked(gripper, wkc);
        return true;
      }

      std::this_thread::sleep_for(std::chrono::microseconds(cycle_us_));
    }

    neutralize_locked(gripper);
    *message = "movement timed out";
    return false;
  }

  void pulse_neutral_locked()
  {
    for (int cycle = 0; cycle < 4; ++cycle) {
      exchange_once_locked();
      std::this_thread::sleep_for(std::chrono::microseconds(cycle_us_));
    }
  }

  void fill_response_from_state(
    const GripperRuntime & gripper,
    bool success,
    const std::string & message,
    const std::shared_ptr<control_interfaces::srv::ECGrippersControl::Response> & response) const
  {
    response->success = success;
    response->message = message;
    response->current_width_mm = units_to_mm(gripper.tx->current_finger_width);
    response->claw_status = gripper.tx->claw_status;
    response->claw_error = gripper.tx->claw_error;
    response->motor_error = gripper.tx->motor_error;
  }

  void publish_status_locked(const GripperRuntime & gripper, int wkc) const
  {
    // 限频: 最少间隔 100ms (≤10Hz), 避免 EtherCAT 循环(5ms)里高频发布
    const auto now_ts = std::chrono::steady_clock::now();
    if (now_ts - last_status_ts_ < std::chrono::milliseconds(MIN_STATUS_PERIOD_MS)) {
      return;
    }
    last_status_ts_ = now_ts;

    control_interfaces::msg::ECGrippersStatus msg;
    msg.header.stamp = now();
    msg.header.frame_id = gripper.config.name;
    msg.gripper_name = gripper.config.name;
    msg.slave_index = gripper.config.slave_index;
    msg.online = operational_;
    msg.working_counter = wkc;
    msg.claw_status = gripper.tx->claw_status;
    msg.claw_status_text = claw_status_text(gripper.tx->claw_status);
    msg.claw_error = gripper.tx->claw_error;
    msg.motor_status = gripper.tx->motor_status;
    msg.motor_error = gripper.tx->motor_error;
    msg.current_width_mm = units_to_mm(gripper.tx->current_finger_width);
    msg.current_position_mm = units_to_mm(gripper.tx->current_position);
    msg.target_position_mm = units_to_mm(gripper.tx->target_position);
    msg.bus_voltage_v = units_to_mm(gripper.tx->bus_voltage);
    msg.driver_temperature_c = units_to_mm(gripper.tx->driver_temperature);
    status_pub_->publish(msg);
  }

  std::string interface_name_;
  std::string expected_device_name_;
  int cycle_us_ = 5000;
  int ready_timeout_cycles_ = 4000;
  int move_timeout_cycles_ = 6000;
  int position_tolerance_units_ = 3;
  int monitor_period_ms_ = 100;
  int expected_wkc_ = 0;
  int last_wkc_ = 0;
  bool operational_ = false;
  char io_map_[4096] {};
  std::vector<GripperRuntime> grippers_;
  mutable std::mutex ethercat_mutex_;
  rclcpp::Publisher<control_interfaces::msg::ECGrippersStatus>::SharedPtr status_pub_;
  rclcpp::Service<control_interfaces::srv::ECGrippersControl>::SharedPtr control_srv_;
  rclcpp::TimerBase::SharedPtr cycle_timer_;
  rclcpp::TimerBase::SharedPtr status_timer_;
  // status 发布限频 (≤10Hz), const 方法里用 mutable
  static constexpr int MIN_STATUS_PERIOD_MS = 100;  // 最少 100ms 间隔 = 10Hz 上限
  mutable std::chrono::steady_clock::time_point last_status_ts_ {};
};

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);

  try {
    rclcpp::spin(std::make_shared<GripperNode>());
  } catch (const std::exception & error) {
    RCLCPP_FATAL(rclcpp::get_logger("gripper_node"), "%s", error.what());
  }

  rclcpp::shutdown();
  return 0;
}