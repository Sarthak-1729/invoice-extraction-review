import { useState } from 'react'
import { FIELD_LABELS, fieldId, HEADER_FIELDS, LINE_FIELDS } from '../labels.js'
import { AlertIcon } from './icons.jsx'
import Button from './Button.jsx'
import Notice from './Notice.jsx'

const EMPTY = '(empty)'

function initialValues(document) {
  const raw = document.raw || {}
  const values = {}
  for (const name of HEADER_FIELDS) values[name] = raw[name] ?? ''
  ;(raw.line_items || []).forEach((line, index) => {
    for (const name of LINE_FIELDS) values[`line_items[${index}].${name}`] = line[name] ?? ''
  })
  return values
}

function rawValue(document, path) {
  const match = /^line_items\[(\d+)\]\.(\w+)$/.exec(path)
  const source = match ? document.raw?.line_items?.[Number(match[1])] : document.raw
  return source?.[match ? match[2] : path] ?? null
}

function normalizedValue(document, path) {
  const match = /^line_items\[(\d+)\]\.(\w+)$/.exec(path)
  const source = match ? document.normalized?.line_items?.[Number(match[1])] : document.normalized
  return source?.[match ? match[2] : path] ?? null
}

function FlagList({ id, flags }) {
  if (!flags.length) return null
  return (
    <ul id={id} className="flag-list">
      {flags.map((flag) => (
        <li key={`${flag.code}-${flag.message}`} className={`flag flag--${flag.severity}`}>
          <AlertIcon />
          <span>
            <strong>{flag.severity === 'error' ? 'Error' : 'Warning'}</strong>{' '}
            <code>{flag.code}</code>: {flag.message}
          </span>
        </li>
      ))}
    </ul>
  )
}

function FieldValues({ id, raw, normalized, corrected }) {
  return (
    <dl id={id} className="field-values">
      <div>
        <dt>Extracted text</dt>
        <dd>{raw ?? EMPTY}</dd>
      </div>
      <div>
        <dt>Normalized</dt>
        <dd>{normalized ?? EMPTY}</dd>
      </div>
      {corrected ? (
        <div>
          <dt>Source</dt>
          <dd>Corrected by reviewer</dd>
        </div>
      ) : null}
    </dl>
  )
}

function HeaderField({ document, path, value, onChange, flags, locked }) {
  const id = fieldId(path)
  const describedBy = [`${id}-values`, flags.length ? `${id}-flags` : null].filter(Boolean).join(' ')
  return (
    <div className={flags.length ? 'field field--flagged' : 'field'}>
      <label htmlFor={id}>
        {/* trailing space keeps the name "Total Flagged", not "TotalFlagged" */}
        {flags.length ? `${FIELD_LABELS[path]} ` : FIELD_LABELS[path]}
        {flags.length ? (
          <span className="flag-marker">
            <AlertIcon /> Flagged
          </span>
        ) : null}
      </label>
      <input
        id={id}
        type="text"
        value={value}
        onChange={(event) => onChange(path, event.target.value)}
        readOnly={locked}
        aria-describedby={describedBy}
        aria-invalid={flags.some((f) => f.severity === 'error') ? 'true' : undefined}
        autoComplete="off"
        spellCheck="false"
      />
      <FieldValues
        id={`${id}-values`}
        raw={rawValue(document, path)}
        normalized={normalizedValue(document, path)}
        corrected={(document.corrected_paths || []).includes(path)}
      />
      <FlagList id={`${id}-flags`} flags={flags} />
    </div>
  )
}

function LineItemsTable({ document, values, onChange, flagsFor, locked }) {
  const lines = document.raw?.line_items || []
  const tableFlags = flagsFor('line_items')
  return (
    <section aria-labelledby="line-items-heading" className="line-items">
      <h3 id="line-items-heading">
        {tableFlags.length ? 'Line items ' : 'Line items'}
        {tableFlags.length ? (
          <span className="flag-marker">
            <AlertIcon /> Flagged
          </span>
        ) : null}
      </h3>
      <FlagList id="line-items-flags" flags={tableFlags} />
      {lines.length === 0 ? (
        <p>No line items were extracted.</p>
      ) : (
        <div
          id={fieldId('line_items')}
          className="table-scroll"
          role="region"
          aria-labelledby="line-items-caption"
          aria-describedby={tableFlags.length ? 'line-items-flags' : undefined}
          tabIndex={0}
        >
          <table className="line-table">
            <caption id="line-items-caption">
              {lines.length === 1 ? '1 line item' : `${lines.length} line items`}
              {locked ? '' : ' (each cell is editable)'}
            </caption>
            <thead>
              <tr>
                <th scope="col" id="col-line">
                  Line
                </th>
                {LINE_FIELDS.map((name) => (
                  <th scope="col" key={name} id={`col-${name}`}>
                    {FIELD_LABELS[name]}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {lines.map((_, index) => (
                <tr key={index}>
                  <th scope="row" id={`row-${index}`}>
                    Line {index + 1}
                  </th>
                  {LINE_FIELDS.map((name) => {
                    const path = `line_items[${index}].${name}`
                    const id = fieldId(path)
                    const flags = flagsFor(path)
                    const describedBy = [`${id}-values`, flags.length ? `${id}-flags` : null]
                      .filter(Boolean)
                      .join(' ')
                    return (
                      <td key={name} className={flags.length ? 'cell--flagged' : undefined}>
                        {flags.length ? (
                          <span className="flag-marker">
                            <AlertIcon /> Flagged
                          </span>
                        ) : null}
                        <input
                          id={id}
                          type="text"
                          value={values[path] ?? ''}
                          onChange={(event) => onChange(path, event.target.value)}
                          readOnly={locked}
                          aria-labelledby={`row-${index} col-${name}`}
                          aria-describedby={describedBy}
                          aria-invalid={flags.some((f) => f.severity === 'error') ? 'true' : undefined}
                          autoComplete="off"
                          spellCheck="false"
                          className={name === 'description' ? 'input--wide' : 'input--narrow'}
                        />
                        <FieldValues
                          id={`${id}-values`}
                          raw={rawValue(document, path)}
                          normalized={normalizedValue(document, path)}
                          corrected={(document.corrected_paths || []).includes(path)}
                        />
                        <FlagList id={`${id}-flags`} flags={flags} />
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

// Props: document, locked, busy, notice, onSave(changes) -> Promise,
// onDirtyChange(isDirty)
export default function FieldsForm({ document, locked, busy, notice, onSave, onDirtyChange }) {
  const [values, setValues] = useState(() => initialValues(document))
  const [baseline, setBaseline] = useState(document)
  if (document !== baseline) {
    // A new version from the server (after a save): start from its values.
    setBaseline(document)
    setValues(initialValues(document))
  }

  const original = initialValues(document)
  const changes = Object.keys(values)
    .filter((path) => values[path].trim() !== (original[path] ?? '').trim())
    .map((path) => ({ field_path: path, value: values[path].trim() || null }))

  function handleChange(path, value) {
    const next = { ...values, [path]: value }
    setValues(next)
    const dirty = Object.keys(next).some((p) => next[p].trim() !== (original[p] ?? '').trim())
    onDirtyChange(dirty)
  }

  function handleReset() {
    setValues(original)
    onDirtyChange(false)
  }

  function handleSubmit(event) {
    event.preventDefault()
    onSave(changes)
  }

  const flagsFor = (path) => (document.flags || []).filter((flag) => flag.field_path === path)

  return (
    <form onSubmit={handleSubmit} aria-labelledby="fields-heading" noValidate>
      <h2 id="fields-heading">Invoice fields</h2>
      {locked ? (
        <p className="hint">This document is approved, so its fields are read-only.</p>
      ) : (
        <p className="hint">
          Edit the text as it appears on the invoice. Saving re-runs every check.
        </p>
      )}
      <section aria-labelledby="header-fields-heading">
        <h3 id="header-fields-heading">Header</h3>
        <div className="field-grid">
          {HEADER_FIELDS.map((path) => (
            <HeaderField
              key={path}
              document={document}
              path={path}
              value={values[path]}
              onChange={handleChange}
              flags={flagsFor(path)}
              locked={locked}
            />
          ))}
        </div>
      </section>
      <LineItemsTable
        document={document}
        values={values}
        onChange={handleChange}
        flagsFor={flagsFor}
        locked={locked}
      />
      {locked ? null : (
        <div className="form-footer">
          <p className="actions">
            <Button type="submit" className="button button--primary" unavailable={busy}>
              Save changes
            </Button>
            <Button onClick={handleReset} unavailable={busy || changes.length === 0}>
              Undo unsaved edits
            </Button>
            <span className="hint">
              {changes.length === 0
                ? 'No unsaved edits.'
                : changes.length === 1
                  ? '1 unsaved edit.'
                  : `${changes.length} unsaved edits.`}
            </span>
          </p>
          <Notice notice={notice} />
        </div>
      )}
    </form>
  )
}
