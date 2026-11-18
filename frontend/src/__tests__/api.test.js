// The real API client against stubbed fetch / XMLHttpRequest (no network).
import { describe, expect, it, vi } from 'vitest'
import { ApiError, createApi } from '../api.js'

function respond(status, body, { json = true } = {}) {
  return vi.fn(async () => ({
    ok: status >= 200 && status < 300,
    status,
    text: async () => (json ? JSON.stringify(body) : body),
    json: async () => body,
  }))
}

function fakeXhr({ status, response, progress = [] }) {
  const instances = []
  class FakeXHR {
    constructor() {
      this.upload = {}
      instances.push(this)
    }
    open(method, url) {
      this.method = method
      this.url = url
    }
    send(body) {
      this.body = body
      for (const p of progress) this.upload.onprogress?.({ lengthComputable: true, ...p })
      this.upload.onload?.()
      this.status = status
      this.response = response
      if (status === 0) this.onerror()
      else this.onload()
    }
  }
  vi.stubGlobal('XMLHttpRequest', FakeXHR)
  return instances
}

describe('createApi', () => {
  it('builds URLs from the base URL and lists documents with a status filter', async () => {
    const fetch = respond(200, { documents: [{ id: 'x' }] })
    vi.stubGlobal('fetch', fetch)
    const api = createApi('http://localhost:8000/')
    expect(await api.listDocuments('needs_review')).toEqual([{ id: 'x' }])
    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/documents?status=needs_review',
      expect.objectContaining({ method: 'GET' }),
    )
    expect(api.pdfUrl('abc')).toBe('http://localhost:8000/api/documents/abc/pdf')
  })

  it('sends PATCH and approve bodies as JSON', async () => {
    const fetch = respond(200, { id: 'x' })
    vi.stubGlobal('fetch', fetch)
    const api = createApi('http://h')
    await api.updateFields('x', [{ field_path: 'total', value: '1' }])
    await api.approve('x', true)
    expect(fetch.mock.calls[0][1]).toEqual({
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ changes: [{ field_path: 'total', value: '1' }] }),
    })
    expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({ acknowledge_open_flags: true })
  })

  it('turns the backend error shape into ApiError with code, message and extras', async () => {
    vi.stubGlobal(
      'fetch',
      respond(409, { error: { code: 'DUPLICATE', message: 'Already uploaded.', document_id: 'd1' } }),
    )
    const error = await createApi('http://h').getDocument('x').catch((e) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect([error.status, error.code, error.message, error.extra]).toEqual([
      409,
      'DUPLICATE',
      'Already uploaded.',
      { document_id: 'd1' },
    ])
  })

  it('maps a non-JSON error page (for example a proxy 502) to HTTP_<status>', async () => {
    vi.stubGlobal('fetch', respond(502, '<html>Bad gateway</html>', { json: false }))
    const error = await createApi('http://h').listDocuments().catch((e) => e)
    expect([error.status, error.code]).toEqual([502, 'HTTP_502'])
  })

  it('maps an unreachable server to NETWORK_ERROR', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => Promise.reject(new TypeError('Failed to fetch'))))
    const error = await createApi('http://h').listDocuments().catch((e) => e)
    expect([error.code, error.message]).toEqual(['NETWORK_ERROR', 'Could not reach the API at http://h.'])
  })

  it('treats 204 No Content as success', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, status: 204 })))
    expect(await createApi('http://h').deleteDocument('x')).toBeNull()
  })

  it('uploads with progress; 201 is a new document, 200 a duplicate of a failed one', async () => {
    const xhrs = fakeXhr({ status: 201, response: { id: 'n' }, progress: [{ loaded: 5, total: 10 }] })
    const onProgress = vi.fn()
    const file = new File(['%PDF'], 'a.pdf', { type: 'application/pdf' })
    expect(await createApi('http://h').uploadDocument(file, onProgress)).toEqual({
      document: { id: 'n' },
      duplicateOfFailed: false,
    })
    expect(xhrs[0].method).toBe('POST')
    expect(xhrs[0].url).toBe('http://h/api/documents')
    expect(xhrs[0].body.get('file').name).toBe('a.pdf')
    expect(onProgress.mock.calls).toEqual([[{ loaded: 5, total: 10 }], [{ done: true }]])

    fakeXhr({ status: 200, response: { id: 'f', status: 'failed' } })
    expect((await createApi('http://h').uploadDocument(file)).duplicateOfFailed).toBe(true)
  })

  it('rejects an upload with the backend code, or NETWORK_ERROR', async () => {
    const file = new File(['x'], 'a.pdf')
    fakeXhr({ status: 403, response: { error: { code: 'TEST_SET_DOCUMENT', message: 'No.' } } })
    expect((await createApi('http://h').uploadDocument(file).catch((e) => e)).code).toBe(
      'TEST_SET_DOCUMENT',
    )
    fakeXhr({ status: 0, response: null })
    expect((await createApi('http://h').uploadDocument(file).catch((e) => e)).code).toBe('NETWORK_ERROR')
  })
})
