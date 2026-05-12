import asyncio
import json
import random

from rclpy.node import Node
from furance_interfaces.srv import GenericCommand

MOCK_MAPS = [
    {"id": "workshop_map", "name": "车间地图", "width": 20.0, "height": 15.0},
]

MOCK_WAYPOINTS = {
    "workshop_map": [
        {"id": "wp_01", "name": "充电桩", "x": 1.0, "y": 1.0},
        {"id": "wp_02", "name": "炉台A", "x": 5.0, "y": 3.0},
        {"id": "wp_03", "name": "炉台B", "x": 5.0, "y": 7.0},
        {"id": "wp_04", "name": "料架区", "x": 10.0, "y": 2.0},
        {"id": "wp_05", "name": "暂存区", "x": 10.0, "y": 6.0},
    ],
}


class NavigationNode(Node):
    def __init__(self):
        super().__init__('navigation_node')
        self.get_logger().info('NavigationNode started')

        self._move_srv = self.create_service(GenericCommand, '/MoveCommand', self._handle_move)
        self._map_list_srv = self.create_service(GenericCommand, '/GetMapList', self._handle_map_list)
        self._wp_list_srv = self.create_service(GenericCommand, '/GetWaypointList', self._handle_waypoint_list)

    def _handle_move(self, request, response):
        params = json.loads(request.params_json) if request.params_json else {}
        map_id = params.get('map_id', 'workshop_map')
        waypoint_id = params.get('waypoint_id', 'wp_01')
        speed = params.get('speed', 0.5)

        self.get_logger().info(
            f'MoveCommand: moving to waypoint {waypoint_id} on map {map_id} at speed {speed}'
        )

        delay = random.uniform(1.0, 3.0)
        self.get_logger().info(f'Navigation started, estimated time {delay:.1f}s')

        # Simulate navigation delay (blocking the callback is acceptable for sim)
        import time
        time.sleep(delay)

        self.get_logger().info(f'Navigation completed: arrived at {waypoint_id}')
        response.success = True
        response.message = f'Arrived at {waypoint_id}'
        response.result_json = json.dumps({
            'map_id': map_id,
            'waypoint_id': waypoint_id,
            'position': {'x': 5.0, 'y': 3.0, 'theta': 0.0},
        })
        return response

    def _handle_map_list(self, request, response):
        self.get_logger().info('GetMapList: returning map list')
        response.success = True
        response.message = 'OK'
        response.result_json = json.dumps({'maps': MOCK_MAPS})
        return response

    def _handle_waypoint_list(self, request, response):
        params = json.loads(request.params_json) if request.params_json else {}
        map_id = params.get('map_id', 'workshop_map')
        waypoints = MOCK_WAYPOINTS.get(map_id, [])
        self.get_logger().info(f'GetWaypointList: returning {len(waypoints)} waypoints for map {map_id}')
        response.success = True
        response.message = 'OK'
        response.result_json = json.dumps({'waypoints': waypoints})
        return response


def main(args=None):
    import rclpy
    rclpy.init(args=args)
    node = NavigationNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
