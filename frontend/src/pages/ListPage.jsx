import { useCallback, useEffect, useRef, useState } from 'react'
import DocumentList from '../components/DocumentList.jsx'
import ExportPanel from '../components/ExportPanel.jsx'
import Notice from '../components/Notice.jsx'
import UploadForm from '../components/UploadForm.jsx'
import { errorText, STATUS_LABELS } from '../labels.js'

function saveFile(text, fileName, type) {
  const url = URL.createObjectURL(new Blob([text], { type }))
  const link = window.document.createElement('a')
  link.href = url
  link.download = fileName
  window.document.body.append(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export default function ListPage({ api, focusHeading, flash, documentHref }) {
  const [filter, setFilter] = useState('')
  const [documents, setDocuments] = useState(null)
  const [loadFailed, setLoadFailed] = useState(false)
  const [listNotice, setListNotice] = useState(flash ? { kind: 'success', text: flash } : null)
  const headingRef = useRef(null)
  const latestRequest = useRef(0)

  const refresh = useCallback(
    (status) => {
      // Arrow keys on the filter fire one request per option; only the
      // newest answer may update the list.
      const request = ++latestRequest.current
      return api.listDocuments(status || undefined).then(
        (docs) => {
          if (request !== latestRequest.current) return null
          setLoadFailed(false)
          setDocuments(docs)
          return docs
        },
        (error) => {
          if (request !== latestRequest.current) return null
          setLoadFailed(true)
          setDocuments([])
          setListNotice({
            kind: 'error',
            text: `${errorText(error.code, error.message)} Error code: ${error.code}.`,
          })
          return null
        },
      )
    },
    [api],
  )

  useEffect(() => {
    window.document.title = 'Documents – Invoice review'
  }, [])

  useEffect(() => {
    refresh('')
  }, [refresh])

  useEffect(() => {
    if (focusHeading) headingRef.current?.focus()
  }, [focusHeading])

  async function handleFilterChange(status) {
    setFilter(status)
    setDocuments(null)
    const docs = await refresh(status)
    if (docs) {
      const which = status ? ` with status “${STATUS_LABELS[status]}”` : ''
      setListNotice({
        kind: 'info',
        text: `Showing ${docs.length === 1 ? '1 document' : `${docs.length} documents`}${which}.`,
      })
    }
  }

  async function handleUpload(file, onProgress) {
    try {
      return await api.uploadDocument(file, onProgress)
    } finally {
      refresh(filter)
    }
  }

  async function handleRetry(id) {
    try {
      return await api.retryExtraction(id)
    } finally {
      refresh(filter)
    }
  }

  async function handleExport(format) {
    const text = await api.exportText(format)
    const count =
      format === 'json'
        ? JSON.parse(text).documents.length
        : // Document ids are 32 hex characters at the start of each data row.
          new Set(text.match(/^[0-9a-f]{32}(?=,)/gm) || []).size
    const fileName = `invoices.${format}`
    if (count > 0) saveFile(text, fileName, format === 'json' ? 'application/json' : 'text/csv')
    return { count, fileName }
  }

  return (
    <>
      <h1 ref={headingRef} tabIndex={-1}>
        Invoices
      </h1>
      <p className="lead">
        Upload an invoice PDF, check the extracted fields against the document, correct them, and
        approve. Only synthetic documents are used in this project.
      </p>
      <section aria-labelledby="upload-heading" className="card">
        <h2 id="upload-heading">Upload a PDF</h2>
        <UploadForm onUpload={handleUpload} onRetry={handleRetry} documentHref={documentHref} />
      </section>
      <section aria-labelledby="documents-heading" className="card">
        <h2 id="documents-heading">Documents</h2>
        <Notice notice={listNotice} />
        <DocumentList
          documents={documents}
          loadFailed={loadFailed}
          filter={filter}
          onFilterChange={handleFilterChange}
          documentHref={documentHref}
        />
      </section>
      <section aria-labelledby="export-heading" className="card">
        <h2 id="export-heading">Export</h2>
        <ExportPanel onExport={handleExport} />
      </section>
    </>
  )
}
