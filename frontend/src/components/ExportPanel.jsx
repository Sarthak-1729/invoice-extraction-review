import { useState } from 'react'
import { errorText } from '../labels.js'
import Button from './Button.jsx'
import Notice from './Notice.jsx'

// Props: onExport(format) -> Promise<{ count, fileName }>; count 0 means
// nothing is approved yet (no file is saved then).
export default function ExportPanel({ onExport }) {
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState(null)

  async function handleExport(format) {
    setBusy(true)
    setNotice({ kind: 'info', text: `Preparing ${format.toUpperCase()} export…` })
    try {
      const { count, fileName } = await onExport(format)
      setNotice(
        count === 0
          ? { kind: 'info', text: 'Nothing to export yet: no document is approved.' }
          : {
              kind: 'success',
              text: `Saved ${fileName} with ${count === 1 ? '1 approved document' : `${count} approved documents`}.`,
            },
      )
    } catch (error) {
      setNotice({ kind: 'error', text: `${errorText(error.code, error.message)} Error code: ${error.code}.` })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="export">
      <p>Exports contain approved documents only.</p>
      <p className="actions">
        <Button unavailable={busy} onClick={() => handleExport('json')}>
          Download JSON
        </Button>
        <Button unavailable={busy} onClick={() => handleExport('csv')}>
          Download CSV
        </Button>
      </p>
      <Notice notice={notice} />
    </div>
  )
}
