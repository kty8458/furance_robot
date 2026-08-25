from setuptools import find_packages, setup
from glob import glob
import os

package_name = 'mixed_execution'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'config'), ['config/mixed_config.yaml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    tests_require=['pytest'],
    zip_safe=True,
    maintainer='baosight',
    maintainer_email='banwf@foxmail.com',
    description='Mixed function execution service: vision+chassis hybrid scripts exposed to workflow',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'mixed_executor_node = mixed_execution.mixed_executor_node:main',
        ],
    },
)
