// In-memory stand-in for createApi(): same methods, synthetic data, no network.
import { vi } from 'vitest'
import { ApiError } from '../api.js'

let counter = 0

export function makeDocument(overrides = {}) {
  counter += 1
  const id = overrides.id || `doc${String(counter).padStart(29, '0')}`
  const raw = {
    invoice_number: 'INV-1001',
    vendor_name: 'Pellucia Works LLC',
    bill_to_name: 'Velloran Logistics',
    invoice_date: 'September 16, 2026',
    due_date: null,
    currency: 'USD',
    subtotal: '$100.00',
    tax: '$10.00',
    total: '$110.00',
    line_items: [
      { description: 'Server monitoring', quantity: '2', unit_price: '$50.00', amount: '$100.00' },
    ],
  }
  const normalized = {
    invoice_number: 'INV-1001',
    vendor_name: 'Pellucia Works LLC',
    bill_to_name: 'Velloran Logistics',
    invoice_date: '2026-09-16',
    due_date: null,
    currency: 'USD',
    subtotal: '100.00',
    tax: '10.00',
    total: '110.00',
    line_items: [
      { description: 'Server monitoring', quantity: '2', unit_price: '50.00', amount: '100.00' },
    ],
  }
  const doc = {
    id,
    file_name: 'dev-01.pdf',
    status: 'extracted',
    flag_count: 0,
    error_code: null,
    retry_available: false,
    created_at: '2026-11-17T10:00:00+00:00',
    approved_at: null,
    updated_at: '2026-11-17T10:00:00+00:00',
    sha256: 'a'.repeat(64),
    size_bytes: 3000,
    page_count: 1,
    error: null,
    provider: 'fake',
    model: 'fake-model',
    prompt_version: 'extraction_v4',
    prompt_hash: 'b'.repeat(64),
    raw,
    normalized,
    flags: [],
    corrected_paths: [],
    corrections: [],
    acknowledged_open_flags: false,
    ...overrides,
  }
  doc.flag_count = doc.flags.length
  return doc
}

export function flag(field_path, code, severity = 'error', message = `${code} message`) {
  return { field_path, code, severity, message }
}

export function failedDocument(overrides = {}) {
  return makeDocument({
    file_name: 'dev-07.pdf',
    status: 'failed',
    error_code: 'LLM_RATE_LIMITED',
    error: { code: 'LLM_RATE_LIMITED', message: '429 RESOURCE_EXHAUSTED' },
    retry_available: true,
    raw: null,
    normalized: null,
    ...overrides,
  })
}

export function summary(doc) {
  const { id, file_name, status, flag_count, error_code, retry_available, created_at, approved_at } =
    doc
  return { id, file_name, status, flag_count, error_code, retry_available, created_at, approved_at }
}

export function apiError(status, code, message = `${code} from server`, extra = {}) {
  return new ApiError(status, code, message, extra)
}

// A promise you resolve or reject later, to control response order.
export function deferred() {
  let resolve
  let reject
  const promise = new Promise((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

// Every method is a vi.fn with a sensible default; tests override with
// mockImplementation / mockResolvedValueOnce / mockRejectedValueOnce.
export function createFakeApi(documents = []) {
  const store = new Map(documents.map((d) => [d.id, d]))
  return {
    baseUrl: 'http://api.test',
    store,
    listDocuments: vi.fn(async (status) =>
      [...store.values()].filter((d) => !status || d.status === status).map(summary),
    ),
    getDocument: vi.fn(async (id) => {
      if (!store.has(id)) throw apiError(404, 'NOT_FOUND', 'No document with this id.')
      return store.get(id)
    }),
    uploadDocument: vi.fn(async (file, onProgress) => {
      onProgress({ loaded: 50, total: 100 })
      onProgress({ done: true })
      const doc = makeDocument({ file_name: file.name })
      store.set(doc.id, doc)
      return { document: doc, duplicateOfFailed: false }
    }),
    retryExtraction: vi.fn(async (id) => {
      const doc = makeDocument({ ...store.get(id), status: 'extracted', error: null, error_code: null })
      store.set(id, doc)
      return doc
    }),
    deleteDocument: vi.fn(async (id) => {
      store.delete(id)
      return null
    }),
    updateFields: vi.fn(async (id) => store.get(id)),
    approve: vi.fn(async (id, acknowledge) => {
      const doc = {
        ...store.get(id),
        status: 'approved',
        approved_at: '2026-11-17T11:00:00+00:00',
        acknowledged_open_flags: acknowledge,
      }
      store.set(id, doc)
      return doc
    }),
    pdfUrl: (id) => `http://api.test/api/documents/${id}/pdf`,
    exportText: vi.fn(async () => JSON.stringify({ documents: [] })),
  }
}
