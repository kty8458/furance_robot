import api from '.'

export const navigationApi = {
  getMaps: () => api.get('/maps'),
  getWaypoints: (mapId) => api.get(`/maps/${mapId}/waypoints`),
  move: (mapId, waypointId, speed) => api.post('/robot/robot_001/move', { map_id: mapId, waypoint_id: waypointId, speed }),
}
