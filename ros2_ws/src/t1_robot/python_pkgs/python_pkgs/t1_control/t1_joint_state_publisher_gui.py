import argparse
import random
import signal
import sys
import threading

import rclpy

from python_qt_binding.QtCore import pyqtSlot
from python_qt_binding.QtCore import Qt
from python_qt_binding.QtCore import Signal
from python_qt_binding.QtGui import QFont
from python_qt_binding.QtWidgets import QApplication
from python_qt_binding.QtWidgets import QFormLayout
from python_qt_binding.QtWidgets import QGridLayout
from python_qt_binding.QtWidgets import QHBoxLayout
from python_qt_binding.QtWidgets import QLabel
from python_qt_binding.QtWidgets import QLineEdit
from python_qt_binding.QtWidgets import QMainWindow
from python_qt_binding.QtWidgets import QPushButton
from python_qt_binding.QtWidgets import QSlider
from python_qt_binding.QtWidgets import QScrollArea
from python_qt_binding.QtWidgets import QVBoxLayout
from python_qt_binding.QtWidgets import QWidget

from joint_state_publisher.joint_state_publisher import JointStatePublisher

from joint_state_publisher_gui.flow_layout import FlowLayout
from interface_pkg.srv import MoveToJointPositions, ClearError, RobotEnableControl
from sensor_msgs.msg import JointState

RANGE = 10000
LINE_EDIT_WIDTH = 45
SLIDER_WIDTH = 200
INIT_NUM_SLIDERS = 7

DEFAULT_WINDOW_MARGIN = 11
DEFAULT_CHILD_MARGIN = 9
DEFAULT_BTN_HEIGHT = 25
DEFAULT_SLIDER_HEIGHT = 64

MIN_WIDTH = SLIDER_WIDTH + DEFAULT_CHILD_MARGIN * 4 + DEFAULT_WINDOW_MARGIN * 2
MIN_HEIGHT = DEFAULT_BTN_HEIGHT * 2 + DEFAULT_WINDOW_MARGIN * 2 + DEFAULT_CHILD_MARGIN * 2


class Slider(QWidget):
    def __init__(self, name):
        super().__init__()

        self.joint_layout = QVBoxLayout()
        self.row_layout = QHBoxLayout()

        font = QFont("Helvetica", 9, QFont.Bold)
        self.label = QLabel(name)
        self.label.setFont(font)
        self.row_layout.addWidget(self.label)

        self.display = QLineEdit("0.00")
        self.display.setAlignment(Qt.AlignRight)
        self.display.setFont(font)
        self.display.setReadOnly(True)
        self.display.setFixedWidth(LINE_EDIT_WIDTH)
        self.row_layout.addWidget(self.display)

        self.joint_layout.addLayout(self.row_layout)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setFont(font)
        self.slider.setRange(0, RANGE)
        self.slider.setValue(int(RANGE / 2))
        self.slider.setFixedWidth(SLIDER_WIDTH)

        self.joint_layout.addWidget(self.slider)

        self.setLayout(self.joint_layout)

    def remove(self):
        self.joint_layout.removeWidget(self.slider)
        self.slider.setParent(None)

        self.row_layout.removeWidget(self.display)
        self.display.setParent(None)

        self.row_layout.removeWidget(self.label)
        self.label.setParent(None)

        self.row_layout.setParent(None)


class JointStatePublisherGui(QMainWindow):
    sliderUpdateTrigger = Signal()
    initialize = Signal()

    def __init__(self, title, jsp):
        super(JointStatePublisherGui, self).__init__()

        self.joint_map = {}

        self.setWindowTitle(title)

        self.move_button = QPushButton('GO!', self)
        self.move_button.clicked.connect(self.moveToTargetEvent)

        self.enable_button = QPushButton('ENABLE', self)
        self.enable_button.clicked.connect(self.enableEvent)

        self.disable_button = QPushButton('DISABLE', self)
        self.disable_button.clicked.connect(self.disableEvent)

        self.clear_button = QPushButton('CLEAR', self)
        self.clear_button.clicked.connect(self.clearEvent)

        self.ctr_button = QPushButton('Center', self)
        self.ctr_button.clicked.connect(self.centerEvent)

        self.sync_button = QPushButton('Sync', self)
        self.sync_button.clicked.connect(self.syncEvent)

        self.scroll_layout = FlowLayout()

        self.scroll_widget = QWidget()
        self.scroll_widget.setLayout(self.scroll_layout)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.scroll_widget)

        self.main_layout = QVBoxLayout()

        self.main_layout.addWidget(self.clear_button)
        self.main_layout.addWidget(self.enable_button)
        self.main_layout.addWidget(self.move_button)
        self.main_layout.addWidget(self.disable_button)
        self.main_layout.addWidget(self.ctr_button)
        self.main_layout.addWidget(self.sync_button)
        self.main_layout.addWidget(self.scroll_area)

        self.central_widget = QWidget()
        self.central_widget.setLayout(self.main_layout)
        self.setCentralWidget(self.central_widget)

        self.jsp = jsp
        self.jsp.set_source_update_cb(self.sliderUpdateCb)
        self.jsp.set_robot_description_update_cb(self.initializeCb)

        self.running = True
        self.sliders = {}

        self.initialize.connect(self.initializeSliders)
        self.sliderUpdateTrigger.connect(self.updateSliders)

        self.initialize.emit()

        self.move_client = self.jsp.create_client(MoveToJointPositions, '/move_joint_positions')
        self.clear_client = self.jsp.create_client(ClearError, '/robot_clear_error')
        self.enable_client = self.jsp.create_client(RobotEnableControl, '/robot_enable_control')

        self.real_joint_sub = self.jsp.create_subscription(
            JointState,
            '/joint_states',
            self.real_joint_callback,
            10
        )

        self.latest_real_joints = None

    def initializeSliders(self):
        self.joint_map = {}

        for sl, _ in self.sliders.items():
            self.scroll_layout.removeWidget(sl)
            sl.remove()

        for name in self.jsp.joint_list:
            if name not in self.jsp.free_joints:
                continue
            joint = self.jsp.free_joints[name]

            if joint['min'] == joint['max']:
                continue

            slider = Slider(name)

            self.joint_map[name] = {'display': slider.display, 'slider': slider.slider, 'joint': joint}

            self.scroll_layout.addWidget(slider)
            slider.slider.valueChanged.connect(lambda event, name=name: self.onSliderValueChangedOne(name))

            self.sliders[slider] = slider

        self.centerEvent(None)

        if len(self.sliders) >= INIT_NUM_SLIDERS:
            num_sliders = INIT_NUM_SLIDERS
        else:
            num_sliders = len(self.sliders)
        scroll_layout_height = num_sliders * DEFAULT_SLIDER_HEIGHT
        scroll_layout_height += (num_sliders + 1) * DEFAULT_CHILD_MARGIN
        self.setMinimumSize(MIN_WIDTH, scroll_layout_height + MIN_HEIGHT)

        self.sliderUpdateTrigger.emit()

    def sliderUpdateCb(self):
        self.sliderUpdateTrigger.emit()

    def initializeCb(self):
        self.initialize.emit()

    def onSliderValueChangedOne(self, name):
        joint_info = self.joint_map[name]
        slidervalue = joint_info['slider'].value()
        joint = joint_info['joint']
        joint['position'] = self.sliderToValue(slidervalue, joint)
        joint_info['display'].setText("%.3f" % joint['position'])

    @pyqtSlot()
    def updateSliders(self):
        for name, joint_info in self.joint_map.items():
            joint = joint_info['joint']
            slidervalue = self.valueToSlider(joint['position'], joint)
            joint_info['slider'].setValue(slidervalue)

    def centerEvent(self, event):
        self.jsp.get_logger().info("Centering")
        for name, joint_info in self.joint_map.items():
            joint = joint_info['joint']
            joint_info['slider'].setValue(self.valueToSlider(joint['zero'], joint))

    def randomizeEvent(self, event):
        self.jsp.get_logger().info("Randomizing")
        for name, joint_info in self.joint_map.items():
            joint = joint_info['joint']
            joint_info['slider'].setValue(
                self.valueToSlider(random.uniform(joint['min'], joint['max']), joint))

    def done_callback(self, fut):
        try:
            res = fut.result()
            if res.success:
                self.jsp.get_logger().info(f"执行成功: {res.message}")
            else:
                self.jsp.get_logger().warn(f"执行失败: {res.message}")
        except Exception as e:
            self.jsp.get_logger().error(f"服务调用异常: {e}")

    def moveToTargetEvent(self, event):
        self.jsp.get_logger().info("Moving...")

        try:
            self.jsp.get_logger().info("Moving arms")
            if not self.move_client.wait_for_service(timeout_sec=3.0):
                self.jsp.get_logger().error("双臂控制服务未上线！")
                return
            req = MoveToJointPositions.Request()
            left_joints, right_joints = [], []
            for name, info in self.joint_map.items():
                pos = info['joint']['position']
                deg = pos * 180.0 / 3.1415926
                if 'ARM-L' in name:
                    left_joints.append(deg)
                elif 'ARM-R' in name:
                    right_joints.append(deg)
            req.left_joints = left_joints
            req.right_joints = right_joints
            self.jsp.get_logger().info(str(req))
            future = self.move_client.call_async(req)
            rclpy.spin_once(self.jsp, timeout_sec=1.0)

            future.add_done_callback(self.done_callback)
        except Exception as e:
            self.jsp.get_logger().error(f"异常,执行出错: {e}")

    def clearEvent(self, event):
        self.jsp.get_logger().info("Clear Error")
        if not self.clear_client.wait_for_service(timeout_sec=3.0):
            self.jsp.get_logger().error("清错服务未上线！")
            return
        req = ClearError.Request()
        req.clear_error = True
        future = self.clear_client.call_async(req)
        rclpy.spin_once(self.jsp, timeout_sec=1.0)
        future.add_done_callback(self.done_callback)

    def enableEvent(self, event):
        self.jsp.get_logger().info("Enable Robot")
        if not self.enable_client.wait_for_service(timeout_sec=3.0):
            self.jsp.get_logger().error("使能服务未上线！")
            return
        req = RobotEnableControl.Request()
        req.enable = True
        future = self.enable_client.call_async(req)
        rclpy.spin_once(self.jsp, timeout_sec=1.0)
        future.add_done_callback(self.done_callback)

    def disableEvent(self, event):
        self.jsp.get_logger().info("Disable Robot")
        if not self.enable_client.wait_for_service(timeout_sec=3.0):
            self.jsp.get_logger().error("使能服务未上线！")
            return
        req = RobotEnableControl.Request()
        req.enable = False
        future = self.enable_client.call_async(req)
        rclpy.spin_once(self.jsp, timeout_sec=1.0)
        future.add_done_callback(self.done_callback)

    def syncEvent(self, event):
        self.jsp.get_logger().info("Sync JointStates")
        if self.latest_real_joints is None:
            self.jsp.get_logger().warn("没有接收到真实机器人 joint_states")
            return

        real = self.latest_real_joints
        self.jsp.get_logger().info("同步真实机器人关节角...")

        for name, joint_info in self.joint_map.items():
            if name in real.name:
                idx = real.name.index(name)
                real_pos = real.position[idx]

                joint_info['joint']['position'] = real_pos
                slider_val = self.valueToSlider(real_pos, joint_info['joint'])
                joint_info['slider'].setValue(slider_val)

                joint_info['display'].setText(f"{real_pos:.3f}")

        self.jsp.get_logger().info("同步完成！GUI 已更新为真实机器人姿态")

    def valueToSlider(self, value, joint):
        return int((value - joint['min']) * float(RANGE) / (joint['max'] - joint['min']))

    def sliderToValue(self, slider, joint):
        pctvalue = slider / float(RANGE)
        return joint['min'] + (joint['max']-joint['min']) * pctvalue

    def closeEvent(self, event):
        self.running = False

    def loop(self):
        while self.running:
            rclpy.spin_once(self.jsp, timeout_sec=0.1)

    def real_joint_callback(self, msg: JointState):
        self.latest_real_joints = msg


def main():
    rclpy.init()

    stripped_args = rclpy.utilities.remove_ros_args(args=sys.argv)
    parser = argparse.ArgumentParser()
    parser.add_argument('urdf_file', help='URDF file to use', nargs='?', default=None)

    parsed_args = parser.parse_args(args=stripped_args[1:])

    app = QApplication(sys.argv)
    jsp_gui = JointStatePublisherGui('Target Joint State',
                                     JointStatePublisher(parsed_args.urdf_file))

    jsp_gui.show()

    threading.Thread(target=jsp_gui.loop).start()
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
