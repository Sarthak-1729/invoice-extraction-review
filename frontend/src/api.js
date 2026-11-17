// HTTP client for the backend API (docs/DESIGN.md). The app receives this
// object as a prop, so tests can pass a fake with the same methods.
//
// Every failure is thrown as an ApiError with the backend's error code, or
// NETWORK_ERROR when the API cannot be reached.

export class ApiError extends Error {
  constructor(status, code, message, extra = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.extra = extra
  }
}

function errorFrom(status, body) {
  const error = body && typeof body === 'object' ? body.error : null
  if (error && error.code) {
    const { code, message, ...extra } = error
    return new ApiError(status, code, message || code, extra)
  }
  return new ApiError(status, `HTTP_${status}`, `The server answered with status ${status}.`)
}

function networkError(baseUrl) {
  return new ApiError(0, 'NETWORK_ERROR', `Could not reach the API at ${baseUrl}.`)
}

export function createApi(baseUrl) {
  const root = baseUrl.replace(/\/+$/, '')
  const url = (path) => `${root}/api${path}`

  async function request(path, { method = 'GET', body } = {}) {
    let response
    try {
      response = await fetch(url(path), {
        method,
        headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body),
      })
    } catch {
      throw networkError(root)
    }
    if (response.status === 204) return null
    const text = await response.text()
    let data = null
    try {
      data = text ? JSON.parse(text) : null
    } catch {
      data = null
    }
    if (!response.ok) throw errorFrom(response.status, data)
    return data
  }

  // XMLHttpRequest instead of fetch: fetch cannot report upload progress.
  function uploadDocument(file, onProgress = () => {}) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      xhr.open('POST', url('/documents'))
      xhr.responseType = 'json'
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) onProgress({ loaded: event.loaded, total: event.total })
      }
      xhr.upload.onload = () => onProgress({ done: true })
      xhr.onerror = () => reject(networkError(root))
      xhr.onload = () => {
        const body = xhr.response
        if (xhr.status >= 200 && xhr.status < 300) {
          // 201: a new document. 200: a duplicate of a failed document.
          resolve({ document: body, duplicateOfFailed: xhr.status === 200 })
        } else {
          reject(errorFrom(xhr.status, body))
        }
      }
      const form = new FormData()
      form.append('file', file)
      xhr.send(form)
    })
  }

  async function download(format) {
    let response
    try {
      response = await fetch(url(`/export?format=${format}`))
    } catch {
      throw networkError(root)
    }
    if (!response.ok) {
      let body = null
      try {
        body = await response.json()
      } catch {
        body = null
      }
      throw errorFrom(response.status, body)
    }
    return response.text()
  }

  return {
    baseUrl: root,
    listDocuments: (status) =>
      request(status ? `/documents?status=${encodeURIComponent(status)}` : '/documents').then(
        (data) => data.documents,
      ),
    getDocument: (id) => request(`/documents/${encodeURIComponent(id)}`),
    uploadDocument,
    retryExtraction: (id) => request(`/documents/${encodeURIComponent(id)}/retry`, { method: 'POST' }),
    deleteDocument: (id) => request(`/documents/${encodeURIComponent(id)}`, { method: 'DELETE' }),
    updateFields: (id, changes) =>
      request(`/documents/${encodeURIComponent(id)}/fields`, { method: 'PATCH', body: { changes } }),
    approve: (id, acknowledgeOpenFlags) =>
      request(`/documents/${encodeURIComponent(id)}/approve`, {
        method: 'POST',
        body: { acknowledge_open_flags: acknowledgeOpenFlags },
      }),
    pdfUrl: (id) => url(`/documents/${encodeURIComponent(id)}/pdf`),
    exportText: download,
  }
}
