import { useEffect, useRef, useState } from 'react'
import ReviewScreen from '../components/ReviewScreen.jsx'
import { errorText, STATUS_LABELS } from '../labels.js'

function flagCountText(count) {
  return count === 1 ? '1 open flag' : `${count} open flags`
}

function failure(error) {
  return { kind: 'error', text: `${errorText(error.code, error.message)} Error code: ${error.code}.` }
}

// Loads one document and turns user actions into API calls.
export default function ReviewPage({ api, id, focusHeading, onDeleted, listHref }) {
  const [document, setDocument] = useState(null)
  const [loadError, setLoadError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [notices, setNotices] = useState({ fields: null, approve: null, failed: null })
  const headingRef = useRef(null)

  useEffect(() => {
    let active = true
    api.getDocument(id).then(
      (doc) => active && setDocument(doc),
      (error) => active && setLoadError(error),
    )
    return () => {
      active = false
    }
  }, [api, id])

  const title = document ? document.file_name : loadError ? 'Document not available' : 'Loading document'
  useEffect(() => {
    window.document.title = `${title} – Invoice review`
  }, [title])

  useEffect(() => {
    if (focusHeading) headingRef.current?.focus()
  }, [focusHeading])

  function notify(section, notice) {
    setNotices({ fields: null, approve: null, failed: null, [section]: notice })
  }

  async function run(section, action, describe) {
    setBusy(true)
    notify(section, { kind: 'info', text: 'Working…' })
    try {
      const updated = await action()
      setDocument(updated)
      notify(section, describe(updated))
      return updated
    } catch (error) {
      notify(section, failure(error))
      return null
    } finally {
      setBusy(false)
    }
  }

  const on = {
    save: async (changes) => {
      if (changes.length === 0) {
        notify('fields', { kind: 'info', text: 'No changes to save.' })
        return
      }
      const updated = await run(
        'fields',
        () => api.updateFields(id, changes),
        (doc) => ({
          kind: 'success',
          text: `Saved ${changes.length === 1 ? '1 change' : `${changes.length} changes`}. Status: ${STATUS_LABELS[doc.status]}, ${flagCountText(doc.flags.length)}.`,
        }),
      )
      if (updated) setDirty(false)
    },
    approve: (acknowledge) =>
      run(
        'approve',
        () => api.approve(id, acknowledge),
        () => ({ kind: 'success', text: 'Approved. The document is now locked and included in exports.' }),
      ),
    approveError: (text) => notify('approve', { kind: 'error', text }),
    retry: () =>
      run(
        'failed',
        () => api.retryExtraction(id),
        (doc) =>
          doc.status === 'failed'
            ? failure({ code: doc.error_code, message: doc.error?.message })
            : { kind: 'success', text: `Extraction succeeded. Status: ${STATUS_LABELS[doc.status]}.` },
      ).then((doc) => {
        // The failed panel is replaced by the fields; keep focus on the page.
        if (doc && doc.status !== 'failed') headingRef.current?.focus()
      }),
    delete: async () => {
      setBusy(true)
      try {
        await api.deleteDocument(id)
        onDeleted(`Deleted ${document.file_name}.`)
      } catch (error) {
        notify('failed', failure(error))
        setBusy(false)
      }
    },
    dirtyChange: setDirty,
  }

  return (
    <>
      <p className="breadcrumb">
        <a href={listHref}>← All documents</a>
      </p>
      <h1 ref={headingRef} tabIndex={-1}>
        {document ? (
          <>
            <span className="visually-hidden">Review </span>
            {document.file_name}
          </>
        ) : (
          title
        )}
      </h1>
      {loadError ? (
        <div role="alert" className="notice notice--error">
          <span>{failure(loadError).text}</span>
        </div>
      ) : document ? (
        <ReviewScreen
          document={document}
          pdfUrl={api.pdfUrl(id)}
          busy={busy}
          dirty={dirty}
          notices={notices}
          on={on}
        />
      ) : (
        <p role="status">Loading…</p>
      )}
    </>
  )
}
