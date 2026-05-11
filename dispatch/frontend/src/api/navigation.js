import api from '.'

export const navigationApi = {
  getMaps: () => api.get('/dispatch/maps'),
  getWaypoints: (mapId) => api.get(`/dispatch/maps/${mapId}/waypoints`),
  move: (robotId, mapId, waypointId, speed) => api.post(`/dispatch/robot/${robotId}/move`, { map_id: mapId, waypoint_id: waypointId, speed }),
}