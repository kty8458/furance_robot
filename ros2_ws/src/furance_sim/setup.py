from glob import glob
import os

from setuptools import setup, find_packages

package_name = 'furance_sim'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('furance_sim/launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='furance',
    maintainer_email='dev@furance.local',
    description='Simulation nodes for Furance robot system',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'navigation_node = furance_sim.navigation_node:main',
            'arm_node = furance_sim.arm_node:main',
            'gripper_node = furance_sim.gripper_node:main',
            'command_node = furance_sim.command_node:main',
            'status_node = furance_sim.status_node:main',
            'node_manager = furance_sim.node_manager:main',
        ],
    },
)
