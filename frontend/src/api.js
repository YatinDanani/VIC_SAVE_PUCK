const BASE = '/api'

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

function connectSimulation(config, onMessage) {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const ws = new WebSocket(`${protocol}//${window.location.host}/ws/simulation`)

  ws.onopen = () => {
    ws.send(JSON.stringify(config))
  }

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data)
    onMessage(data)
  }

  ws.onerror = (err) => {
    onMessage({ type: 'error', message: 'WebSocket connection error' })
  }

  ws.onclose = () => {
    onMessage({ type: 'closed' })
  }

  return {
    send: (msg) => ws.readyState === WebSocket.OPEN && ws.send(JSON.stringify(msg)),
    close: () => ws.close(),
    setSpeed: (speed) => ws.readyState === WebSocket.OPEN && ws.send(JSON.stringify({ action: 'speed', value: speed })),
    stop: () => ws.readyState === WebSocket.OPEN && ws.send(JSON.stringify({ action: 'stop' })),
  }
}

export const api = {
  teams:                ()     => request('/teams'),
  history:              ()     => request('/history/summary'),
  forecast:             (body) => request('/forecast', { method: 'POST', body: JSON.stringify(body) }),
  scenarios:            ()     => request('/scenarios'),
  backtest:             ()     => request('/validation/backtest'),
  eventRecommendations: ()     => request('/ai/event-recommendations'),
  connectSimulation,
}
