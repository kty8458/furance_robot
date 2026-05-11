import { ref, onMounted, onUnmounted } from 'vue'

export function useLogs() {
  const logs = ref([])
  const connected = ref(false)
  const maxLogs = 1000
  let ws = null
  let reconnectTimer = null

  function connect() {
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
        logs.value.push(frame.payload)
        if (logs.value.length > maxLogs) logs.value.splice(0, logs.value.length - maxLogs)
      }
    }
  }

  function clearLogs() { logs.value = [] }

  onMounted(connect)
  onUnmounted(() => {
    if (ws) ws.close()
    if (reconnectTimer) clearTimeout(reconnectTimer)
  })

  return { logs, connected, clearLogs }
}
