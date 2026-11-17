import { useEffect, useRef, useState } from 'react'
import { errorText, fieldId, fieldPathLabel, formatTime } from '../labels.js'
import { AlertIcon, LockIcon } from './icons.jsx'
import Button from './Button.jsx'
import Notice from './Notice.jsx'

export function PdfViewer({ url, fileName }) {
  return (
    <section aria-labelledby="pdf-heading" className="pdf-panel">
      <h2 id="pdf-heading">Original PDF</h2>
      <p>
        <a href={url} target="_blank" rel="noopener noreferrer">
          Open PDF in new tab<span className="visually-hidden"> ({fileName})</span>
        </a>{' '}
        <span className="hint">(opens a new tab; use it if the preview below is empty)</span>
      </p>
      <iframe className="pdf-frame" src={url} title={`PDF preview of ${fileName}`} />
    </section>
  )
}

// Every open flag, with a button that moves focus to the field it belongs to.
export function FlagSummary({ flags }) {
  function focusField(path) {
    const target = document.getElementById(fieldId(path))
    if (target) {
      target.scrollIntoView({ block: 'center' })
      target.focus()
    }
  }
  return (
    <section aria-labelledby="flags-heading" className="flag-summary">
      <h2 id="flags-heading">
        {flags.length === 0
          ? 'No open flags'
          : flags.length === 1
            ? '1 open flag'
            : `${flags.length} open flags`}
      </h2>
      {flags.length === 0 ? (
        <p>Every check passed. Compare the fields with the PDF before approving.</p>
      ) : (
        <ul className="flag-summary-list">
          {flags.map((flag, index) => (
            <li key={`${flag.field_path}-${flag.code}-${index}`} className={`flag flag--${flag.severity}`}>
              <AlertIcon />
              <span>
                <strong>{flag.severity === 'error' ? 'Error' : 'Warning'}</strong> in{' '}
                {fieldPathLabel(flag.field_path)}: <code>{flag.code}</code> — {flag.message}{' '}
                <button type="button" className="link-button" onClick={() => focusField(flag.field_path)}>
                  Go to {fieldPathLabel(flag.field_path).toLowerCase()}
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

// Props: document, dirty, busy, notice, onApprove(acknowledge), onError(text)
export function ApprovePanel({ document, dirty, busy, notice, onApprove, onError }) {
  const [acknowledged, setAcknowledged] = useState(false)
  const checkboxRef = useRef(null)
  const approvedHeadingRef = useRef(null)
  const flagCount = document.flags.length
  const approved = document.status === 'approved'
  const wasApproved = useRef(approved)

  useEffect(() => {
    // The Approve button disappears on approval; keep keyboard focus here.
    if (approved && !wasApproved.current) approvedHeadingRef.current?.focus()
    wasApproved.current = approved
  }, [approved])

  if (approved) {
    return (
      <section aria-labelledby="approve-heading" className="approved-banner">
        <h2 id="approve-heading" ref={approvedHeadingRef} tabIndex={-1}>
          <LockIcon /> Approved
        </h2>
        <p>
          Approved on <time dateTime={document.approved_at}>{formatTime(document.approved_at)}</time>.
          {document.acknowledged_open_flags
            ? ` The reviewer approved it with ${flagCount === 1 ? '1 open flag' : `${flagCount} open flags`} acknowledged.`
            : ''}{' '}
          The document is locked and included in exports.
        </p>
        <Notice notice={notice} />
      </section>
    )
  }

  function handleApprove() {
    if (dirty) {
      onError('Save or undo your edits before approving.')
      return
    }
    if (flagCount > 0 && !acknowledged) {
      onError('Tick the confirmation box to approve a document with open flags.')
      checkboxRef.current?.focus()
      return
    }
    onApprove(flagCount > 0)
  }

  return (
    <section aria-labelledby="approve-heading" className="approve-panel">
      <h2 id="approve-heading">Approve</h2>
      {flagCount > 0 ? (
        <>
          <p id="approve-explainer">
            {flagCount === 1 ? '1 flag is' : `${flagCount} flags are`} still open. Correct the
            fields, or confirm that you checked the flags against the PDF.
          </p>
          <div className="checkbox">
            <input
              ref={checkboxRef}
              id="acknowledge-flags"
              type="checkbox"
              checked={acknowledged}
              onChange={(event) => setAcknowledged(event.target.checked)}
              aria-describedby="approve-explainer"
            />
            <label htmlFor="acknowledge-flags">
              I checked the open flags against the PDF and approve anyway.
            </label>
          </div>
        </>
      ) : (
        <p>All checks passed. Approving locks the document and adds it to exports.</p>
      )}
      <p className="actions">
        <Button className="button button--primary" unavailable={busy} onClick={handleApprove}>
          Approve document
        </Button>
      </p>
      <Notice notice={notice} />
    </section>
  )
}

// Props: document, busy, notice, onRetry(), onDelete()
export function FailedPanel({ document, busy, notice, onRetry, onDelete }) {
  const [confirming, setConfirming] = useState(false)
  const cancelRef = useRef(null)
  const deleteRef = useRef(null)
  const wasConfirming = useRef(false)

  useEffect(() => {
    if (confirming) cancelRef.current?.focus()
    else if (wasConfirming.current) deleteRef.current?.focus()
    wasConfirming.current = confirming
  }, [confirming])

  return (
    <section aria-labelledby="failed-heading" className="failed-panel">
      <h2 id="failed-heading">Extraction failed</h2>
      <p>{errorText(document.error_code)}</p>
      <dl className="field-values">
        <div>
          <dt>Error code</dt>
          <dd>
            <code>{document.error_code}</code>
          </dd>
        </div>
        <div>
          <dt>Server message</dt>
          <dd>{document.error?.message}</dd>
        </div>
      </dl>
      <p className="actions">
        <Button className="button button--primary" unavailable={busy} onClick={onRetry}>
          Retry extraction
        </Button>
        {confirming ? null : (
          <Button
            ref={deleteRef}
            className="button button--danger"
            unavailable={busy}
            onClick={() => setConfirming(true)}
          >
            Delete
          </Button>
        )}
      </p>
      {confirming ? (
        <div className="confirm" role="group" aria-labelledby="confirm-delete-text">
          <p id="confirm-delete-text">
            Delete {document.file_name} and its stored PDF? This cannot be undone.
          </p>
          <p className="actions">
            <Button className="button button--danger" unavailable={busy} onClick={onDelete}>
              Yes, delete it
            </Button>
            <button ref={cancelRef} type="button" className="button" onClick={() => setConfirming(false)}>
              Cancel
            </button>
          </p>
        </div>
      ) : null}
      <Notice notice={notice} />
    </section>
  )
}

export function CorrectionsTable({ corrections }) {
  return (
    <section aria-labelledby="corrections-heading">
      <h2 id="corrections-heading">Corrections history</h2>
      {corrections.length === 0 ? (
        <p>No corrections yet.</p>
      ) : (
        <div className="table-scroll" role="region" aria-labelledby="corrections-caption" tabIndex={0}>
          <table>
            <caption id="corrections-caption">
              {corrections.length === 1 ? '1 correction' : `${corrections.length} corrections`}, oldest
              first
            </caption>
            <thead>
              <tr>
                <th scope="col">Field</th>
                <th scope="col">Original value</th>
                <th scope="col">Corrected value</th>
                <th scope="col">Time</th>
              </tr>
            </thead>
            <tbody>
              {corrections.map((correction, index) => (
                <tr key={`${correction.field_path}-${correction.created_at}-${index}`}>
                  <th scope="row">{fieldPathLabel(correction.field_path)}</th>
                  <td>{correction.original_value ?? '(empty)'}</td>
                  <td>{correction.corrected_value ?? '(empty)'}</td>
                  <td>
                    <time dateTime={correction.created_at}>{formatTime(correction.created_at)}</time>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
