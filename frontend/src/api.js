const API = ''

function authHeaders(token) {
  const headers = {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  }
  if (token) headers.Authorization = `Bearer ${token}`
  return headers
}

async function request(path, { method = 'GET', body, token, noAuth = false } = {}) {
  const res = await fetch(`${API}${path}`, {
    method,
    headers: authHeaders(noAuth ? null : token),
    body: body != null ? JSON.stringify(body) : undefined,
  })
  const text = await res.text()
  let data = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = text
  }
  if (!res.ok) {
    const detail = data?.detail
    const msg =
      typeof detail === 'string'
        ? detail
        : detail
          ? JSON.stringify(detail)
          : text || `HTTP ${res.status}`
    throw new Error(msg)
  }
  return data
}

export const api = {
  login: (username, password) =>
    request('/api/login', {
      method: 'POST',
      body: { username, password },
      noAuth: true,
    }),
  me: (token) => request('/api/me', { token }),
  map: (token) => request('/api/map', { token }),
  notifications: (token, target) =>
    request(`/api/notifications${target ? `?target=${target}` : ''}`, { token }),
  events: (token) => request('/api/events', { token }),
  stats: (token) => request('/api/stats', { token }),
  resolve: (token, id, resolution) =>
    request(`/api/events/${id}/resolve`, {
      method: 'POST',
      token,
      body: { resolution },
    }),
  watchCheck: (token, force = false) =>
    request(`/api/watch/check?force=${force}`, { method: 'POST', token }),
  ingest: (ip, value, online = true) =>
    request(`/api/ingest/${encodeURIComponent(ip)}`, {
      method: 'POST',
      body: { value, online },
      noAuth: true,
    }),
  resetSensors: (token) =>
    request('/api/sensors/reset', { method: 'POST', token }),
}
