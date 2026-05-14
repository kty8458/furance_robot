from setuptools import find_packages, setup
from glob import glob
import os

package_name = 'python_pkgs'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name), ['python_pkgs/vision/best2.onnx'])
    ],
    install_requires=['setuptools'],
    extras_require={
        'qt': ['PyQt5'],
    },
    zip_safe=True,
    maintainer='baosight',
    maintainer_email='banwf@foxmail.com',
    description='TODO: Package description',
    license='TODO: License declaration',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'qr_dete = python_pkgs.vision.QR_dete:main',
            'sim_arm_controller = python_pkgs.t1_control.sim_arm_controller:main',
            't1_joint_state_bridge = python_pkgs.t1_control.t1_joint_states_publisher:main',
            't1_joint_state_publisher_gui = python_pkgs.t1_control.t1_joint_state_publisher_gui:main',
            't1_move_client = python_pkgs.t1_control.t1_move_client:main',
            't1_display = python_pkgs.t1_control.t1_display:main',
        ],
    },
)
