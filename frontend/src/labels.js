// Human-readable text for field paths, statuses and error codes.

export const HEADER_FIELDS = [
  'invoice_number',
  'vendor_name',
  'bill_to_name',
  'invoice_date',
  'due_date',
  'currency',
  'subtotal',
  'tax',
  'total',
]

export const LINE_FIELDS = ['description', 'quantity', 'unit_price', 'amount']

export const FIELD_LABELS = {
  invoice_number: 'Invoice number',
  vendor_name: 'Vendor name',
  bill_to_name: 'Bill-to name',
  invoice_date: 'Invoice date',
  due_date: 'Due date',
  currency: 'Currency',
  subtotal: 'Subtotal',
  tax: 'Tax',
  total: 'Total',
  description: 'Description',
  quantity: 'Quantity',
  unit_price: 'Unit price',
  amount: 'Amount',
  line_items: 'Line items',
}

export const STATUSES = ['extracted', 'needs_review', 'approved', 'failed']

export const STATUS_LABELS = {
  extracted: 'Extracted',
  needs_review: 'Needs review',
  approved: 'Approved',
  failed: 'Failed',
}

const LINE_PATH = /^line_items\[(\d+)\]\.(\w+)$/

export function fieldPathLabel(path) {
  const match = LINE_PATH.exec(path)
  if (match) return `Line ${Number(match[1]) + 1}, ${FIELD_LABELS[match[2]].toLowerCase()}`
  return FIELD_LABELS[path] || path
}

// DOM id for the input that edits a field path (also used by flag links).
export function fieldId(path) {
  return `field-${path.replace(/[^a-z0-9]+/gi, '-')}`
}

const ERROR_TEXT = {
  NETWORK_ERROR: 'The API could not be reached. Check that the backend server is running.',
  DUPLICATE: 'This PDF was already uploaded.',
  FILE_TOO_LARGE: 'The file is larger than the upload limit.',
  NOT_A_PDF: 'This file is not a PDF. Choose a file that ends in .pdf.',
  SCANNED_PDF_UNSUPPORTED:
    'This PDF has no text layer (it looks scanned). Only PDFs with selectable text are supported.',
  ENCRYPTED_PDF: 'This PDF is password-protected. Remove the password and upload it again.',
  TOO_MANY_PAGES: 'This PDF has more pages than the limit.',
  INVALID_PDF: 'This PDF could not be read. It may be damaged.',
  TEST_SET_DOCUMENT:
    'This PDF is part of the frozen evaluation test set, so uploads of it are refused. Use a dev PDF.',
  LLM_RATE_LIMITED: 'The extraction service is rate-limited. Wait a minute, then retry.',
  LLM_UNAVAILABLE: 'The extraction service is unavailable right now. Retry later.',
  LLM_TIMEOUT: 'The extraction service took too long to answer. Retry later.',
  LLM_AUTH_FAILED: 'The extraction service rejected the API key. Check the backend configuration.',
  LLM_BAD_REQUEST: 'The extraction service rejected the request. Check the model name.',
  LLM_NOT_CONFIGURED: 'No extraction service is configured (API key or model missing).',
  LLM_OUTPUT_INCOMPLETE: 'The extraction stopped before it finished. Retry the extraction.',
  LLM_ERROR: 'The extraction service failed.',
  SCHEMA_VALIDATION_FAILED: 'The extraction returned data in the wrong shape twice.',
  OPEN_FLAGS: 'This document still has open flags.',
  DOCUMENT_LOCKED: 'Approved documents cannot be edited.',
  NO_CHANGES: 'Nothing was changed.',
  INVALID_VALUE: 'One of the values is not valid.',
}

// A sentence for the user. The server message is kept when it adds detail.
export function errorText(code, serverMessage) {
  const known = ERROR_TEXT[code]
  if (!known) return serverMessage || 'Something went wrong.'
  if (!serverMessage || serverMessage === known) return known
  return `${known} (${serverMessage})`
}

export function formatTime(iso) {
  if (!iso) return ''
  const date = new Date(iso)
  return Number.isNaN(date.getTime())
    ? iso
    : date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}
