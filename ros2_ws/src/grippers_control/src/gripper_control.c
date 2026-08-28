/**
 * JODELL EPG-L80-400 EtherCAT gripper controller based on SOEM.
 *
 * Preferred usage, sharing parameters with the ROS2 node:
 *   sudo ./gripper_control right open
 *   sudo ./gripper_control right close
 *   sudo ./gripper_control right move <width_mm>
 *   sudo ./gripper_control right status
 *   sudo ./gripper_control right clear  (清除故障)
 *
 * Optional config path:
 *   sudo ./gripper_control --config config/gripper.yaml left move 80
 *
 * Backward-compatible usage, overriding interface_name from the config file:
 *   sudo ./gripper_control <ifname> right move 40
 */

#include <ctype.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "ethercat.h"

#define DEFAULT_CONFIG_PATH    "config/gripper.yaml"
#define MAX_GRIPPERS           8
#define MAX_NAME_LEN           32
#define MAX_IFNAME_LEN         128
#define MAX_DEVICE_NAME_LEN    64

#define DEFAULT_CYCLE_US              5000
#define DEFAULT_READY_TIMEOUT_CYCLES  4000
#define DEFAULT_MOVE_TIMEOUT_CYCLES   6000
#define DEFAULT_POSITION_TOLERANCE    3     /* 0.3 mm */

/* 说明书第9章 RXPDO Comand: bit7=参数同步(常规置1), bit0~1=3 为清除故障指令 */
#define CMD_NEUTRAL                   0x0080
#define CMD_CLEAR_FAULT               0x0083

#pragma pack(push, 1)

typedef struct
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
} GripperRxPDO;

typedef struct
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
} GripperTxPDO;

#pragma pack(pop)

typedef struct
{
    char name[MAX_NAME_LEN];
    int slave_index;
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
} GripperConfig;

typedef struct
{
    char interface_name[MAX_IFNAME_LEN];
    char expected_device_name[MAX_DEVICE_NAME_LEN];
    int cycle_us;
    int ready_timeout_cycles;
    int move_timeout_cycles;
    int position_tolerance;
    int gripper_count;
    GripperConfig grippers[MAX_GRIPPERS];
} ControllerConfig;

_Static_assert(sizeof(GripperRxPDO) == 40, "RxPDO size must be 40 bytes");
_Static_assert(sizeof(GripperTxPDO) == 40, "TxPDO size must be 40 bytes");

static char IOmap[4096];

static void copy_text(char *dst, size_t dst_size, const char *src)
{
    if (dst_size == 0)
    {
        return;
    }

    snprintf(dst, dst_size, "%s", src != NULL ? src : "");
}

static char *trim(char *text)
{
    while (*text != '\0' && isspace((unsigned char)*text))
    {
        ++text;
    }

    char *end = text + strlen(text);
    while (end > text && isspace((unsigned char)*(end - 1)))
    {
        --end;
    }
    *end = '\0';

    return text;
}

static void remove_comment(char *text)
{
    int in_quotes = 0;

    for (char *p = text; *p != '\0'; ++p)
    {
        if (*p == '"')
        {
            in_quotes = !in_quotes;
        }
        else if (*p == '#' && !in_quotes)
        {
            *p = '\0';
            return;
        }
    }
}

static int parse_int_value(const char *text, int *value)
{
    char *end = NULL;
    long parsed = strtol(text, &end, 0);

    if (end == text)
    {
        return 0;
    }

    while (*end != '\0' && isspace((unsigned char)*end))
    {
        ++end;
    }

    if (*end != '\0')
    {
        return 0;
    }

    *value = (int)parsed;
    return 1;
}

static int parse_u16_value(const char *text, uint16 *value)
{
    int parsed = 0;

    if (!parse_int_value(text, &parsed) || parsed < 0 || parsed > 65535)
    {
        return 0;
    }

    *value = (uint16)parsed;
    return 1;
}

static int parse_string_value(const char *text, char *dst, size_t dst_size)
{
    char buffer[256];
    copy_text(buffer, sizeof(buffer), text);

    char *value = trim(buffer);
    size_t len = strlen(value);

    if (len >= 2 && value[0] == '"' && value[len - 1] == '"')
    {
        value[len - 1] = '\0';
        ++value;
    }

    copy_text(dst, dst_size, value);
    return 1;
}

static int is_identifier(const char *text)
{
    if (*text == '\0')
    {
        return 0;
    }

    for (const char *p = text; *p != '\0'; ++p)
    {
        if (!isalnum((unsigned char)*p) && *p != '_' && *p != '-')
        {
            return 0;
        }
    }

    return 1;
}

static void init_gripper_defaults(GripperConfig *config,
                                  const char *name,
                                  int slave_index)
{
    memset(config, 0, sizeof(*config));
    copy_text(config->name, sizeof(config->name), name);
    config->slave_index = slave_index;
    config->enable = 1;
    config->close_speed = 80;
    config->open_speed = 80;
    config->close_force = 200;
    config->close_width = 1000;  // 100.0 mm (空载闭合下限)
    config->open_width = 1800;  // 180.0 mm
    config->object_width = 0;
    config->object_width_error = 0;
    config->max_finger_width = 1800;   // 180.0 mm
    config->min_finger_width = 1000;   // 100.0 mm (空载闭合下限, 触发空夹保护)
}

static void init_controller_defaults(ControllerConfig *controller)
{
    memset(controller, 0, sizeof(*controller));
    copy_text(controller->interface_name,
              sizeof(controller->interface_name),
              "enx00e01b76020c");
    copy_text(controller->expected_device_name,
              sizeof(controller->expected_device_name),
              "EPG-L80-400");
    controller->cycle_us = DEFAULT_CYCLE_US;
    controller->ready_timeout_cycles = DEFAULT_READY_TIMEOUT_CYCLES;
    controller->move_timeout_cycles = DEFAULT_MOVE_TIMEOUT_CYCLES;
    controller->position_tolerance = DEFAULT_POSITION_TOLERANCE;
    controller->gripper_count = 2;
    init_gripper_defaults(&controller->grippers[0], "right", 2);
    init_gripper_defaults(&controller->grippers[1], "left", 3);
}

static GripperConfig *find_gripper(ControllerConfig *controller,
                                   const char *name)
{
    for (int i = 0; i < controller->gripper_count; ++i)
    {
        if (strcmp(controller->grippers[i].name, name) == 0)
        {
            return &controller->grippers[i];
        }
    }

    return NULL;
}

static const GripperConfig *find_gripper_const(const ControllerConfig *controller,
                                               const char *name)
{
    for (int i = 0; i < controller->gripper_count; ++i)
    {
        if (strcmp(controller->grippers[i].name, name) == 0)
        {
            return &controller->grippers[i];
        }
    }

    return NULL;
}

static GripperConfig *find_or_add_gripper(ControllerConfig *controller,
                                           const char *name)
{
    GripperConfig *existing = find_gripper(controller, name);
    if (existing != NULL)
    {
        return existing;
    }

    if (controller->gripper_count >= MAX_GRIPPERS)
    {
        return NULL;
    }

    GripperConfig *created = &controller->grippers[controller->gripper_count++];
    init_gripper_defaults(created, name, 0);
    return created;
}

static int parse_gripper_list(ControllerConfig *controller, const char *value)
{
    char buffer[256];
    copy_text(buffer, sizeof(buffer), value);

    char *start = strchr(buffer, '[');
    char *end = strrchr(buffer, ']');
    if (start == NULL || end == NULL || end <= start)
    {
        return 0;
    }

    *end = '\0';
    ++start;

    controller->gripper_count = 0;
    char *token = strtok(start, ",");
    while (token != NULL)
    {
        char *name = trim(token);
        size_t len = strlen(name);

        if (len >= 2 && name[0] == '"' && name[len - 1] == '"')
        {
            name[len - 1] = '\0';
            ++name;
        }

        if (!is_identifier(name) || controller->gripper_count >= MAX_GRIPPERS)
        {
            return 0;
        }

        init_gripper_defaults(&controller->grippers[controller->gripper_count++],
                              name,
                              0);
        token = strtok(NULL, ",");
    }

    return controller->gripper_count > 0;
}

static int set_global_config(ControllerConfig *controller,
                             const char *key,
                             const char *value)
{
    if (strcmp(key, "interface_name") == 0)
    {
        return parse_string_value(value,
                                  controller->interface_name,
                                  sizeof(controller->interface_name));
    }
    if (strcmp(key, "expected_device_name") == 0)
    {
        return parse_string_value(value,
                                  controller->expected_device_name,
                                  sizeof(controller->expected_device_name));
    }
    if (strcmp(key, "cycle_us") == 0)
    {
        return parse_int_value(value, &controller->cycle_us);
    }
    if (strcmp(key, "ready_timeout_cycles") == 0)
    {
        return parse_int_value(value, &controller->ready_timeout_cycles);
    }
    if (strcmp(key, "move_timeout_cycles") == 0)
    {
        return parse_int_value(value, &controller->move_timeout_cycles);
    }
    if (strcmp(key, "position_tolerance_units") == 0)
    {
        return parse_int_value(value, &controller->position_tolerance);
    }
    if (strcmp(key, "grippers") == 0)
    {
        return parse_gripper_list(controller, value);
    }

    return 1;
}

static int set_gripper_config(GripperConfig *config,
                              const char *key,
                              const char *value)
{
    if (strcmp(key, "slave_index") == 0)
    {
        return parse_int_value(value, &config->slave_index);
    }
    if (strcmp(key, "enable") == 0)
    {
        return parse_u16_value(value, &config->enable);
    }
    if (strcmp(key, "close_speed") == 0)
    {
        return parse_u16_value(value, &config->close_speed);
    }
    if (strcmp(key, "open_speed") == 0)
    {
        return parse_u16_value(value, &config->open_speed);
    }
    if (strcmp(key, "close_force") == 0)
    {
        return parse_u16_value(value, &config->close_force);
    }
    if (strcmp(key, "close_width_units") == 0)
    {
        return parse_u16_value(value, &config->close_width);
    }
    if (strcmp(key, "open_width_units") == 0)
    {
        return parse_u16_value(value, &config->open_width);
    }
    if (strcmp(key, "object_width_units") == 0)
    {
        return parse_u16_value(value, &config->object_width);
    }
    if (strcmp(key, "object_width_error_units") == 0)
    {
        return parse_u16_value(value, &config->object_width_error);
    }
    if (strcmp(key, "max_finger_width_units") == 0)
    {
        return parse_u16_value(value, &config->max_finger_width);
    }
    if (strcmp(key, "min_finger_width_units") == 0)
    {
        return parse_u16_value(value, &config->min_finger_width);
    }

    return 1;
}

static int load_config_file(ControllerConfig *controller,
                            const char *path,
                            int required)
{
    FILE *file = fopen(path, "r");
    if (file == NULL)
    {
        if (required)
        {
            fprintf(stderr, "Failed to open config file: %s\n", path);
            return 0;
        }

        fprintf(stderr,
                "Config file %s not found; using built-in defaults.\n",
                path);
        return 1;
    }

    char line[512];
    int line_number = 0;
    GripperConfig *current_gripper = NULL;
    int current_gripper_indent = -1;

    while (fgets(line, sizeof(line), file) != NULL)
    {
        ++line_number;
        int indent = 0;
        while (line[indent] == ' ')
        {
            ++indent;
        }

        remove_comment(line);
        char *content = trim(line);

        if (*content == '\0')
        {
            continue;
        }

        char *colon = strchr(content, ':');
        if (colon == NULL)
        {
            fprintf(stderr,
                    "Invalid config line %d in %s: missing ':'\n",
                    line_number,
                    path);
            fclose(file);
            return 0;
        }

        *colon = '\0';
        char *key = trim(content);
        char *value = trim(colon + 1);

        if (!is_identifier(key))
        {
            fprintf(stderr,
                    "Invalid config key on line %d in %s: %s\n",
                    line_number,
                    path,
                    key);
            fclose(file);
            return 0;
        }

        if (*value == '\0')
        {
            if (strcmp(key, "gripper_node") == 0 ||
                strcmp(key, "ros__parameters") == 0)
            {
                current_gripper = NULL;
                current_gripper_indent = -1;
            }
            else
            {
                current_gripper = find_or_add_gripper(controller, key);
                if (current_gripper == NULL)
                {
                    fprintf(stderr,
                            "Too many gripper sections in %s; max is %d.\n",
                            path,
                            MAX_GRIPPERS);
                    fclose(file);
                    return 0;
                }
                current_gripper_indent = indent;
            }
            continue;
        }

        if (current_gripper != NULL && indent <= current_gripper_indent)
        {
            current_gripper = NULL;
            current_gripper_indent = -1;
        }

        int ok = current_gripper != NULL ?
            set_gripper_config(current_gripper, key, value) :
            set_global_config(controller, key, value);

        if (!ok)
        {
            fprintf(stderr,
                    "Invalid value on line %d in %s: %s: %s\n",
                    line_number,
                    path,
                    key,
                    value);
            fclose(file);
            return 0;
        }
    }

    fclose(file);
    return 1;
}

static int validate_config(const ControllerConfig *controller)
{
    if (controller->interface_name[0] == '\0')
    {
        fprintf(stderr, "interface_name is empty.\n");
        return 0;
    }
    if (controller->cycle_us <= 0 ||
        controller->ready_timeout_cycles <= 0 ||
        controller->move_timeout_cycles <= 0 ||
        controller->position_tolerance < 0)
    {
        fprintf(stderr, "Timing parameters in config must be valid positive values.\n");
        return 0;
    }
    if (controller->gripper_count <= 0)
    {
        fprintf(stderr, "No grippers configured.\n");
        return 0;
    }

    for (int i = 0; i < controller->gripper_count; ++i)
    {
        const GripperConfig *config = &controller->grippers[i];

        if (config->slave_index <= 0)
        {
            fprintf(stderr,
                    "%s.slave_index must be positive.\n",
                    config->name);
            return 0;
        }
        if (config->min_finger_width > config->max_finger_width)
        {
            fprintf(stderr,
                    "%s min_finger_width_units exceeds max_finger_width_units.\n",
                    config->name);
            return 0;
        }
        if (config->close_width < config->min_finger_width ||
            config->close_width > config->max_finger_width ||
            config->open_width < config->min_finger_width ||
            config->open_width > config->max_finger_width)
        {
            fprintf(stderr,
                    "%s open/close width is outside configured finger range.\n",
                    config->name);
            return 0;
        }
    }

    return 1;
}

static void print_usage(const char *program)
{
    fprintf(stderr,
            "Usage:\n"
            "  sudo %s [--config config/gripper.yaml] <gripper> open\n"
            "  sudo %s [--config config/gripper.yaml] <gripper> close\n"
            "  sudo %s [--config config/gripper.yaml] <gripper> move <width_mm>\n"
            "  sudo %s [--config config/gripper.yaml] <gripper> status\n"
            "  sudo %s [--config config/gripper.yaml] <gripper> clear\n"
            "\n"
            "Backward-compatible interface override:\n"
            "  sudo %s [--config config/gripper.yaml] <ifname> <gripper> move <width_mm>\n",
            program,
            program,
            program,
            program,
            program,
            program);
}

static const char *claw_status_text(uint16 status)
{
    switch (status)
    {
        case 0:  return "not initialized";
        case 1:  return "waiting for homing";
        case 2:  return "homing";
        case 3:  return "ready";
        case 4:  return "opening";
        case 5:  return "open position reached";
        case 6:  return "closing";
        case 7:  return "grip successful";
        case 8:  return "empty grip";
        case 9:  return "object dropped";
        case 10: return "fault";
        default: return "unknown";
    }
}

static void print_feedback(const GripperTxPDO *tx, int wkc)
{
    printf("WKC=%d, claw=%u (%s), claw_err=0x%04x, "
           "motor=%u, motor_err=0x%04x, width=%.1f mm, "
           "bus=%.1f V, temp=%.1f C\n",
           wkc,
           tx->claw_status,
           claw_status_text(tx->claw_status),
           tx->claw_error,
           tx->motor_status,
           tx->motor_error,
           tx->current_finger_width / 10.0,
           tx->bus_voltage / 10.0,
           tx->driver_temperature / 10.0);
}

static int exchange_once(int expected_wkc)
{
    ec_send_processdata();
    int wkc = ec_receive_processdata(EC_TIMEOUTRET);

    if (wkc < expected_wkc)
    {
        fprintf(stderr, "Warning: WKC=%d, expected=%d\n", wkc, expected_wkc);
    }

    return wkc;
}

static int parse_width_mm(const char *text,
                          uint16 min_width,
                          uint16 max_width,
                          uint16 *width_units)
{
    char *end = NULL;
    double mm = strtod(text, &end);

    if (end == text || *end != '\0')
    {
        return 0;
    }

    int units = (int)lround(mm * 10.0);

    if (units < min_width || units > max_width)
    {
        return 0;
    }

    *width_units = (uint16)units;
    return 1;
}

/* 清除故障 (说明书第9章: Comand bit0~1=3 清除故障, 设备尝试恢复正常,
 * 故障仍存在则再次进入故障状态; 解除急停后也需清除故障)
 * 返回 1=故障已清除(或本无故障), 0=故障未清除/超时 */
static int clear_fault(const ControllerConfig *controller,
                       GripperRxPDO *rx,
                       GripperTxPDO *tx,
                       int expected_wkc)
{
    rx->command = CMD_CLEAR_FAULT;
    for (int cycle = 0; cycle < 20; ++cycle)
    {
        exchange_once(expected_wkc);
        osal_usleep(controller->cycle_us);
    }
    rx->command = CMD_NEUTRAL;

    for (int cycle = 0; cycle < controller->ready_timeout_cycles; ++cycle)
    {
        exchange_once(expected_wkc);

        if (tx->claw_status != 10 && tx->claw_error == 0 && tx->motor_error == 0)
        {
            printf("Fault cleared.\n");
            return 1;
        }

        osal_usleep(controller->cycle_us);
    }

    return 0;
}

static int run_controller(const ControllerConfig *controller,
                          const GripperConfig *config,
                          const char *action,
                          uint16 requested_width)
{
    int result = 1;
    int expected_wkc;
    int chk;

    if (!ec_init(controller->interface_name))
    {
        fprintf(stderr,
                "Failed to open interface %s. Run with sudo.\n",
                controller->interface_name);
        return 1;
    }

    if (ec_config_init(FALSE) <= 0)
    {
        fprintf(stderr, "No EtherCAT slaves found.\n");
        ec_close();
        return 1;
    }

    ec_config_map(&IOmap);
    ec_configdc();
    ec_statecheck(0, EC_STATE_SAFE_OP, EC_TIMEOUTSTATE * 4);

    printf("%d slave(s) found.\n", ec_slavecount);

    // 鲁棒性: 按设备名扫描夹爪 slave (支持 EtherCAT 分线器等非夹爪 slave 混在总线上)
    // 找第一个名字匹配的夹爪 slave, 跳过分线器等非夹爪设备
    int found_gripper_slave = 0;
    for (int s = 1; s <= ec_slavecount; ++s)
    {
        const char *sname = ec_slave[s].name;
        if (controller->expected_device_name[0] == '\0' ||
            strcmp(sname, controller->expected_device_name) == 0)
        {
            found_gripper_slave = s;
            printf("Slave %d = %s (gripper)\n", s, sname);
            break;
        }
        else
        {
            printf("Slave %d = %s (non-gripper, skip)\n", s, sname);
        }
    }

    if (found_gripper_slave == 0)
    {
        fprintf(stderr,
                "No gripper slave (expected %s) found; slave count=%d.\n",
                controller->expected_device_name[0] ? controller->expected_device_name : "any",
                ec_slavecount);
        goto cleanup;
    }

    // 自动映射到找到的夹爪 slave (无论配置里 slave_index 是几)
    // config 是 const, 用本地副本改 slave_index
    GripperConfig config_local = *config;
    if (config_local.slave_index != found_gripper_slave)
    {
        printf("Note: %s.slave_index %d -> %d (auto-bind to first gripper slave).\n",
               config_local.name, config_local.slave_index, found_gripper_slave);
        config_local.slave_index = found_gripper_slave;
    }
    config = &config_local;

    printf("Selected %s gripper: slave %d (%s)\n",
           config->name,
           config->slave_index,
           ec_slave[config->slave_index].name);
    printf("Output PDO: %d bytes, Input PDO: %d bytes\n",
           ec_slave[config->slave_index].Obytes,
           ec_slave[config->slave_index].Ibytes);

    if (controller->expected_device_name[0] != '\0' &&
        strcmp(ec_slave[config->slave_index].name,
               controller->expected_device_name) != 0)
    {
        fprintf(stderr,
                "Slave %d is not %s; actual device is %s.\n",
                config->slave_index,
                controller->expected_device_name,
                ec_slave[config->slave_index].name);
        goto cleanup;
    }

    if (ec_slave[config->slave_index].Obytes < 40 ||
        ec_slave[config->slave_index].Ibytes < 40)
    {
        fprintf(stderr, "Unexpected PDO size for selected gripper.\n");
        goto cleanup;
    }

    GripperRxPDO *rx =
        (GripperRxPDO *)ec_slave[config->slave_index].outputs;
    GripperTxPDO *tx =
        (GripperTxPDO *)ec_slave[config->slave_index].inputs;

    memset(rx, 0, sizeof(*rx));

    rx->command = 0x0080;
    rx->enable = config->enable;
    rx->close_speed = config->close_speed;
    rx->open_speed = config->open_speed;
    rx->close_force = config->close_force;
    rx->close_width = config->close_width;
    rx->open_width = config->open_width;
    rx->object_width = config->object_width;
    rx->object_width_error = config->object_width_error;
    rx->max_finger_width = config->max_finger_width;
    rx->min_finger_width = config->min_finger_width;

    expected_wkc =
        (ec_group[0].outputsWKC * 2) + ec_group[0].inputsWKC;

    ec_send_processdata();
    ec_receive_processdata(EC_TIMEOUTRET);

    ec_slave[0].state = EC_STATE_OPERATIONAL;
    ec_writestate(0);

    chk = 200;
    do
    {
        ec_send_processdata();
        ec_receive_processdata(EC_TIMEOUTRET);
        ec_statecheck(0, EC_STATE_OPERATIONAL, 50000);
    }
    while (chk-- && ec_slave[0].state != EC_STATE_OPERATIONAL);

    if (ec_slave[0].state != EC_STATE_OPERATIONAL)
    {
        fprintf(stderr, "Failed to reach OPERATIONAL state.\n");
        goto cleanup;
    }

    printf("OPERATIONAL state reached.\n");

    if (strcmp(action, "clear") == 0)
    {
        // 手动清错: 发送清除故障指令并等待故障位消失
        if (clear_fault(controller, rx, tx, expected_wkc))
        {
            int wkc = exchange_once(expected_wkc);
            print_feedback(tx, wkc);
            result = 0;
        }
        else
        {
            fprintf(stderr, "Fault persists after clear.\n");
            int wkc = exchange_once(expected_wkc);
            print_feedback(tx, wkc);
        }
        goto neutralize;
    }

    if (strcmp(action, "status") != 0)
    {
        // 开合/移动前自动清错 (含急停解除后需清错的场景), 无故障时为空操作
        if (!clear_fault(controller, rx, tx, expected_wkc))
        {
            fprintf(stderr, "Gripper fault persists after clear.\n");
            goto neutralize;
        }
    }

    int cycle;
    for (cycle = 0; cycle < controller->ready_timeout_cycles; ++cycle)
    {
        int wkc = exchange_once(expected_wkc);

        if ((cycle % 100) == 0)
        {
            print_feedback(tx, wkc);
        }

        if (tx->claw_status == 10 ||
            tx->claw_error != 0 ||
            tx->motor_error != 0)
        {
            fprintf(stderr, "Gripper fault detected.\n");
            print_feedback(tx, wkc);
            goto neutralize;
        }

        // 3(就绪)/5(打开到位)/7(夹持成功)/8(空夹)/9(掉落):
        // 8/9 是动作终止态, 发送 open/close 即可脱离, 不算故障
        if (tx->claw_status == 3 ||
            tx->claw_status == 5 ||
            tx->claw_status == 7 ||
            tx->claw_status == 8 ||
            tx->claw_status == 9)
        {
            break;
        }

        osal_usleep(controller->cycle_us);
    }

    if (cycle >= controller->ready_timeout_cycles)
    {
        fprintf(stderr, "Timed out waiting for gripper readiness.\n");
        goto neutralize;
    }

    if (strcmp(action, "status") == 0)
    {
        int wkc = exchange_once(expected_wkc);
        print_feedback(tx, wkc);
        result = 0;
        goto neutralize;
    }

    uint16 current_width = tx->current_finger_width;
    uint16 target_width = requested_width;

    if (target_width > current_width)
    {
        rx->open_width = target_width;
        rx->command = 0x0080;

        for (cycle = 0; cycle < 4; ++cycle)
        {
            exchange_once(expected_wkc);
            osal_usleep(controller->cycle_us);
        }

        printf("Opening to %.1f mm...\n", target_width / 10.0);
        rx->command = 0x0081;
    }
    else if (target_width < current_width)
    {
        rx->close_width = target_width;
        rx->command = 0x0080;

        for (cycle = 0; cycle < 4; ++cycle)
        {
            exchange_once(expected_wkc);
            osal_usleep(controller->cycle_us);
        }

        printf("Closing to %.1f mm...\n", target_width / 10.0);
        rx->command = 0x0082;
    }
    else
    {
        printf("Gripper is already at %.1f mm.\n", target_width / 10.0);
        result = 0;
        goto neutralize;
    }

    for (cycle = 0; cycle < 20; ++cycle)
    {
        exchange_once(expected_wkc);
        osal_usleep(controller->cycle_us);
    }

    rx->command = 0x0080;

    for (cycle = 0; cycle < controller->move_timeout_cycles; ++cycle)
    {
        int wkc = exchange_once(expected_wkc);

        if ((cycle % 100) == 0)
        {
            print_feedback(tx, wkc);
        }

        if (tx->claw_status == 10 ||
            tx->claw_error != 0 ||
            tx->motor_error != 0)
        {
            fprintf(stderr, "Gripper fault during movement.\n");
            print_feedback(tx, wkc);
            goto neutralize;
        }

        // claw=7(grip successful) / 8(empty grip) / 9(object dropped):
        // 夹爪动作终止状态 (夹到/空夹/掉落), 无论是否到目标宽度都算完成
        if (tx->claw_status == 7 || tx->claw_status == 8 || tx->claw_status == 9)
        {
            printf("Gripper action finished: claw=%u (%s), actual %.1f mm.\n",
                   tx->claw_status,
                   claw_status_text(tx->claw_status),
                   tx->current_finger_width / 10.0);
            print_feedback(tx, wkc);
            result = 0;
            break;
        }

        int error = (int)tx->current_finger_width - (int)target_width;
        if (error < 0)
        {
            error = -error;
        }

        if (error <= controller->position_tolerance)
        {
            printf("Target reached: requested %.1f mm, actual %.1f mm.\n",
                   target_width / 10.0,
                   tx->current_finger_width / 10.0);
            print_feedback(tx, wkc);
            result = 0;
            break;
        }

        osal_usleep(controller->cycle_us);
    }

    if (cycle >= controller->move_timeout_cycles)
    {
        fprintf(stderr, "Movement timed out.\n");
    }

neutralize:
    rx->command = 0x0080;

    for (cycle = 0; cycle < 20; ++cycle)
    {
        exchange_once(expected_wkc);
        osal_usleep(controller->cycle_us);
    }

cleanup:
    ec_slave[0].state = EC_STATE_INIT;
    ec_writestate(0);
    ec_close();
    return result;
}

int main(int argc, char *argv[])
{
    ControllerConfig controller;
    init_controller_defaults(&controller);

    const char *config_path = DEFAULT_CONFIG_PATH;
    int explicit_config = 0;
    int arg_index = 1;

    if (arg_index < argc && strcmp(argv[arg_index], "--config") == 0)
    {
        if (arg_index + 1 >= argc)
        {
            print_usage(argv[0]);
            return 1;
        }

        config_path = argv[arg_index + 1];
        explicit_config = 1;
        arg_index += 2;
    }

    if (!load_config_file(&controller, config_path, explicit_config))
    {
        return 1;
    }

    if (arg_index >= argc)
    {
        print_usage(argv[0]);
        return 1;
    }

    const char *ifname_override = NULL;
    const char *gripper_name = NULL;

    if (find_gripper_const(&controller, argv[arg_index]) != NULL)
    {
        gripper_name = argv[arg_index++];
    }
    else
    {
        ifname_override = argv[arg_index++];
        if (arg_index >= argc)
        {
            print_usage(argv[0]);
            return 1;
        }
        gripper_name = argv[arg_index++];
    }

    if (ifname_override != NULL)
    {
        copy_text(controller.interface_name,
                  sizeof(controller.interface_name),
                  ifname_override);
    }

    const GripperConfig *config =
        find_gripper_const(&controller, gripper_name);
    if (config == NULL)
    {
        fprintf(stderr, "Unknown gripper: %s. Configured grippers:", gripper_name);
        for (int i = 0; i < controller.gripper_count; ++i)
        {
            fprintf(stderr, " %s", controller.grippers[i].name);
        }
        fprintf(stderr, "\n");
        return 1;
    }

    if (arg_index >= argc)
    {
        print_usage(argv[0]);
        return 1;
    }

    const char *action = argv[arg_index++];
    uint16 target_width = 0;

    if (!validate_config(&controller))
    {
        return 1;
    }

    if (strcmp(action, "open") == 0)
    {
        if (arg_index != argc)
        {
            print_usage(argv[0]);
            return 1;
        }
        target_width = config->open_width;
    }
    else if (strcmp(action, "close") == 0)
    {
        if (arg_index != argc)
        {
            print_usage(argv[0]);
            return 1;
        }
        target_width = config->close_width;
    }
    else if (strcmp(action, "move") == 0)
    {
        if (arg_index + 1 != argc ||
            !parse_width_mm(argv[arg_index],
                            config->min_finger_width,
                            config->max_finger_width,
                            &target_width))
        {
            fprintf(stderr,
                    "Width for %s must be between %.1f and %.1f mm.\n",
                    config->name,
                    config->min_finger_width / 10.0,
                    config->max_finger_width / 10.0);
            return 1;
        }
    }
    else if (strcmp(action, "status") == 0)
    {
        if (arg_index != argc)
        {
            print_usage(argv[0]);
            return 1;
        }
        target_width = 0;
    }
    else if (strcmp(action, "clear") == 0)
    {
        if (arg_index != argc)
        {
            print_usage(argv[0]);
            return 1;
        }
        target_width = 0;
    }
    else
    {
        fprintf(stderr, "Unknown action: %s\n", action);
        return 1;
    }

    printf("Using config: %s\n", config_path);
    printf("Using interface: %s\n", controller.interface_name);

    return run_controller(
        &controller,
        config,
        action,
        target_width
    );
}
