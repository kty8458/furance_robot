import { ref } from 'vue'

// Module-level state: persists across page switches
const logs = ref([])
const connected = ref(false)
const maxLogs = 2000
let ws = null
let reconnectTimer = null

function connect() {
  if (ws && ws.readyState === WebSocket.OPEN) return
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  ws = new WebSocket(`${protocol}//${location.host}/ws/v1/logs`)
  ws.onopen = () => { connected.value = true }
  ws.onclose = () => {
    connected.value = false
    reconnectTimer = setTimeout(connect, 5000)
  }
  ws.onmessage = (event) => {
    const frame = JSON.parse(event.data)
    if (frame.type === 'log') {
      const entry = {
        ...frame.payload,
        timestamp: frame.timestamp || Date.now(),
      }
      logs.value.push(entry)
      if (logs.value.length > maxLogs) logs.value.splice(0, logs.value.length - maxLogs)
    }
  }
}

export function useLogs() {
  if (!ws || ws.readyState === WebSocket.CLOSED) {
    connect()
  }
  return { logs, connected, clearLogs: () => { logs.value = [] } }
}
