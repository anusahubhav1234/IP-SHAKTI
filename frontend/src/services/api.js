import axios from 'axios'

export const API_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '')
const TOKEN_KEY = 'sakti.token'

// The JWT is kept in localStorage: simple and survives reloads, but readable by any script on the page.
// That is acceptable here because the app renders no untrusted HTML (answers go through react-markdown, which
// does not render raw HTML). For a hardened deployment, move the token to an httpOnly cookie.
export const tokenStore = {
  get() { try { return localStorage.getItem(TOKEN_KEY) } catch { return null } },
  set(t) { try { localStorage.setItem(TOKEN_KEY, t) } catch { /* private mode */ } },
  clear() { try { localStorage.removeItem(TOKEN_KEY) } catch { /* ignore */ } },
}

export const api = axios.create({ baseURL: API_URL, timeout: 90000 })

api.interceptors.request.use((cfg) => {
  const t = tokenStore.get()
  if (t) cfg.headers.Authorization = `Bearer ${t}`
  return cfg
})

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401 && tokenStore.get()) {
      tokenStore.clear()
      window.dispatchEvent(new Event('sakti:unauthorized'))
    }
    return Promise.reject(err)
  },
)

/** Turns an axios/fetch error into one readable sentence for the UI. */
export function errorMessage(err, fallback = 'Something went wrong. Please try again.') {
  if (err?.name === 'AbortError') return 'Cancelled.'
  if (err?.detail) return String(err.detail)
  const d = err?.response?.data?.detail
  if (typeof d === 'string') return d
  if (Array.isArray(d) && d.length) return d.map((x) => x.msg?.replace(/^Value error, /, '') || 'Invalid input').join('. ')
  if (err?.code === 'ERR_NETWORK' || err?.message === 'Failed to fetch') return 'Cannot reach the server. Check that the backend is running.'
  if (err?.code === 'ECONNABORTED') return 'The server took too long to respond.'
  return fallback
}

const d = (p) => p.then((r) => r.data)

export const authApi = {
  register: (body) => d(api.post('/api/auth/register', body)),
  login: (body) => d(api.post('/api/auth/login', body)),
  logout: () => api.post('/api/auth/logout').catch(() => {}),
  me: () => d(api.get('/api/auth/me')),
  updateProfile: (body) => d(api.patch('/api/auth/me', body)),
  changePassword: (body) => api.post('/api/auth/change-password', body),
}

export const documentsApi = {
  list: (params) => d(api.get('/api/documents', { params })),
  get: (id) => d(api.get(`/api/documents/${id}`)),
  status: (id) => d(api.get(`/api/documents/${id}/status`)),
  chunks: (id, params) => d(api.get(`/api/documents/${id}/chunks`, { params })),
  upload: (file, { title, categoryId, asFaq } = {}, onProgress) => {
    const fd = new FormData()
    fd.append('file', file)
    if (title) fd.append('title', title)
    if (categoryId) fd.append('category_id', categoryId)
    if (asFaq) fd.append('as_faq', 'true')
    return d(api.post('/api/documents/upload', fd, {
      onUploadProgress: (e) => onProgress && e.total && onProgress(Math.round((e.loaded / e.total) * 100)),
    }))
  },
  remove: (id) => api.delete(`/api/documents/${id}`),
  reprocess: (id) => d(api.post(`/api/documents/${id}/reprocess`)),
  // The file endpoint needs the Authorization header, so it is fetched as a blob and shown via an object URL.
  fileUrl: async (id) => {
    const res = await api.get(`/api/documents/${id}/file`, { responseType: 'blob' })
    return URL.createObjectURL(res.data)
  },
  compare: (body) => d(api.post('/api/documents/compare', body)),
}

export const categoriesApi = {
  list: () => d(api.get('/api/categories')),
  create: (name) => d(api.post('/api/categories', { name })),
  remove: (id) => api.delete(`/api/categories/${id}`),
}

export const searchApi = { search: (body) => d(api.post('/api/search', body)) }

export const chatApi = {
  send: (body) => d(api.post('/api/chat', body)),
  conversations: (params) => d(api.get('/api/conversations', { params })),
  conversation: (id) => d(api.get(`/api/conversations/${id}`)),
  removeConversation: (id) => api.delete(`/api/conversations/${id}`),
  feedback: (messageId, rating, comment) => d(api.post(`/api/messages/${messageId}/feedback`, { rating, comment })),
  clearFeedback: (messageId) => api.delete(`/api/messages/${messageId}/feedback`),
}

/**
 * Streams pipeline progress over Server-Sent Events using fetch (axios cannot read streams in browsers).
 * Resolves with the final verified answer; rejects with {status, detail} on failure.
 */
export async function streamChat(body, { onStage, signal } = {}) {
  let res
  try {
    res = await fetch(`${API_URL}/api/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${tokenStore.get()}` },
      body: JSON.stringify(body),
      signal,
    })
  } catch (e) {
    if (e.name === 'AbortError') throw e
    throw { status: 0, detail: 'Cannot reach the server. Check that the backend is running.' }
  }
  if (!res.ok) {
    if (res.status === 401 && tokenStore.get()) { tokenStore.clear(); window.dispatchEvent(new Event('sakti:unauthorized')) }
    let detail = 'The request failed.'
    try {
      const j = await res.json()
      detail = typeof j.detail === 'string' ? j.detail : Array.isArray(j.detail) ? j.detail.map((x) => x.msg).join('. ') : detail
    } catch { /* keep default */ }
    throw { status: res.status, detail }
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let result = null
  let failure = null
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const frames = buffer.split('\n\n')
    buffer = frames.pop()
    for (const frame of frames) {
      const ev = /^event: (.*)$/m.exec(frame)?.[1]
      const data = /^data: (.*)$/m.exec(frame)?.[1]
      if (!ev || !data) continue
      const payload = JSON.parse(data)
      if (ev === 'stage') onStage?.(payload.stage)
      else if (ev === 'result') result = payload
      else if (ev === 'error') failure = payload
    }
  }
  if (failure) throw failure
  if (!result) throw { status: 0, detail: 'The connection closed before an answer arrived.' }
  return result
}

export const analyticsApi = {
  overview: () => d(api.get('/api/analytics/overview')),
  evaluation: () => d(api.get('/api/analytics/evaluation')),
}

export const evaluationApi = {
  benchmarks: () => d(api.get('/api/evaluation/benchmarks')),
  createBenchmark: (body) => d(api.post('/api/evaluation/benchmarks', body)),
  removeBenchmark: (id) => api.delete(`/api/evaluation/benchmarks/${id}`),
  run: (body) => d(api.post('/api/evaluation/runs', body, { timeout: 300000 })),
  runs: () => d(api.get('/api/evaluation/runs')),
}

export const adminApi = {
  overview: () => d(api.get('/api/admin/overview')),
  users: (params) => d(api.get('/api/admin/users', { params })),
  updateUser: (id, body) => d(api.patch(`/api/admin/users/${id}`, body)),
  documents: (params) => d(api.get('/api/admin/documents', { params })),
  health: () => d(api.get('/api/admin/system-health')),
}
