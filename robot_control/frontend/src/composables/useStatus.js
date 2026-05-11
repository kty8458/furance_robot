import { ref, onMounted, onUnmounted } from 'vue'

export function useStatus() {
  const status = ref(null)
  const connected = ref(false)
  let ws = null
  let reconnectTimer = null

  function connect() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    ws = new WebSocket(`${protocol}//${location.host}/ws/v1/status`)
    ws.onopen = () => { connected.value = true }
    ws.onclose = () => {
      connected.value = false
      reconnectTimer = setTimeout(connect, 5000)
    }
    ws.onmessage = (event) => {
      const frame = JSON.parse(event.data)
      if (frame.type === 'status') status.value = frame.payload
    }
  }

  onMounted(connect)
  onUnmounted(() => {
    if (ws) ws.close()
    if (reconnectTimer) clearTimeout(reconnectTimer)
  })

  return { status, connected }
}
