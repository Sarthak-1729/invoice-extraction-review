import { useRef, useState } from 'react'
import { errorText, STATUS_LABELS } from '../labels.js'
import Button from './Button.jsx'
import Notice from './Notice.jsx'

function flagsText(count) {
  return count === 1 ? '1 open flag' : `${count} open flags`
}

// Props:
//   onUpload(file, onProgress) -> Promise<{ document, duplicateOfFailed }>
//   onRetry(id) -> Promise<document>
//   documentHref(id) -> link to the review screen
export default function UploadForm({ onUpload, onRetry, documentHref }) {
  const inputRef = useRef(null)
  const [phase, setPhase] = useState('idle') // idle | uploading | extracting | retrying
  const [fileName, setFileName] = useState('')
  const [percent, setPercent] = useState(0)
  const [result, setResult] = useState(null) // { document, duplicateOfFailed } | { error }
  const busy = phase !== 'idle'

  async function handleSubmit(event) {
    event.preventDefault()
    const file = inputRef.current.files[0]
    if (!file) {
      setResult({ error: { code: 'NO_FILE', message: 'Choose a PDF file first.' } })
      inputRef.current.focus()
      return
    }
    setFileName(file.name)
    setPercent(0)
    setResult(null)
    setPhase('uploading')
    try {
      const outcome = await onUpload(file, (progress) => {
        if (progress.done) setPhase('extracting')
        else setPercent(Math.round((progress.loaded / progress.total) * 100))
      })
      setResult(outcome)
      inputRef.current.value = ''
    } catch (error) {
      setResult({ error })
    } finally {
      setPhase('idle')
    }
  }

  async function handleRetry(id) {
    setPhase('retrying')
    try {
      const document = await onRetry(id)
      setResult({ document, retried: true })
    } catch (error) {
      setResult({ error })
    } finally {
      setPhase('idle')
    }
  }

  let notice = null
  if (phase === 'uploading') notice = { kind: 'info', text: `Uploading ${fileName}…` }
  if (phase === 'extracting')
    notice = {
      kind: 'info',
      text: `Upload complete. Extracting fields from ${fileName}; this can take up to a minute.`,
    }
  if (phase === 'retrying') notice = { kind: 'info', text: 'Retrying extraction…' }
  if (!busy && result?.error) {
    const { code, message } = result.error
    notice = {
      kind: 'error',
      text: `${errorText(code, message)}${code === 'NO_FILE' ? '' : ` Error code: ${code}.`}`,
    }
  }
  const doc = !busy ? result?.document : null
  if (doc) {
    if (doc.status === 'failed') {
      const prefix = result.duplicateOfFailed
        ? `${doc.file_name} was uploaded before and its extraction failed.`
        : `${doc.file_name} was saved, but extraction failed.`
      notice = {
        kind: 'error',
        text: `${prefix} ${errorText(doc.error_code, doc.error?.message)} Error code: ${doc.error_code}.`,
      }
    } else {
      notice = {
        kind: 'success',
        text: `${doc.file_name}${result.retried ? ' extracted after retry' : ''}: ${STATUS_LABELS[doc.status]}, ${flagsText(doc.flag_count)}.`,
      }
    }
  }
  const duplicateId = !busy && result?.error?.code === 'DUPLICATE' ? result.error.extra?.document_id : null

  return (
    <form className="upload" onSubmit={handleSubmit} noValidate>
      <div className="field">
        <label htmlFor="upload-file">PDF file</label>
        <p id="upload-hint" className="hint">
          One text-based PDF (not scanned) per upload. Uploads are limited to 10 MB by default.
        </p>
        <input
          ref={inputRef}
          id="upload-file"
          name="file"
          type="file"
          accept="application/pdf,.pdf"
          aria-describedby="upload-hint"
          disabled={busy}
        />
      </div>
      <Button type="submit" className="button button--primary" unavailable={busy}>
        Upload and extract
      </Button>

      {phase === 'uploading' ? (
        <div className="progress">
          <label htmlFor="upload-progress">Upload progress</label>
          <progress id="upload-progress" max="100" value={percent}>
            {percent}%
          </progress>
          <span aria-hidden="true">{percent}%</span>
        </div>
      ) : null}
      {phase === 'extracting' || phase === 'retrying' ? (
        <div className="progress">
          <label htmlFor="extract-progress">Extraction in progress</label>
          <progress id="extract-progress" />
        </div>
      ) : null}

      <Notice notice={notice} />

      {doc || duplicateId ? (
        <p className="actions">
          {doc ? (
            <a href={documentHref(doc.id)}>
              {doc.status === 'failed' ? 'Open' : 'Review'} {doc.file_name}
            </a>
          ) : null}
          {doc && doc.status === 'failed' ? (
            <Button onClick={() => handleRetry(doc.id)}>Retry extraction</Button>
          ) : null}
          {duplicateId ? <a href={documentHref(duplicateId)}>Open the existing document</a> : null}
        </p>
      ) : null}
    </form>
  )
}
