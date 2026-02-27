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

export const api = {
  teams:   ()      => request('/teams'),
  history: ()      => request('/history/summary'),
  forecast: (body) => request('/forecast', { method: 'POST', body: JSON.stringify(body) }),
}
