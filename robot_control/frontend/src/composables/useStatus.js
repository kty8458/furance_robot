import { ref } from 'vue'

// Module-level state: persists across page switches
const status = ref(null)
const connected = ref(false)
let ws = null
let reconnectTimer = null
let connectCount = 0

function connect() {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  ws = new WebSocket(`${protocol}//${location.host}/ws/v1/status`)
  ws.onopen = () => { /* don't set connected=true until we get data */ }
  ws.onclose = () => {
    connected.value = false
    reconnectTimer = setTimeout(connect, 5000)
  }
  ws.onmessage = (event) => {
    const frame = JSON.parse(event.data)
    if (frame.type === 'status') {
      status.value = frame.payload
      connected.value = true
    }
  }
}

export function useStatus() {
  connectCount++
  if (!ws || ws.readyState === WebSocket.CLOSED) {
    connect()
  }

  // No onUnmounted — keep WS alive across page switches
  // Disconnect only when all consumers are gone is optional;
  // for simplicity, WS stays alive for the whole session.

  return { status, connected }
}
