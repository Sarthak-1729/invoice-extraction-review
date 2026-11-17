import { formatTime, STATUS_LABELS, STATUSES } from '../labels.js'
import StatusBadge from './StatusBadge.jsx'

// Props: documents (array | null while loading), loadFailed, filter ('' = all),
// onFilterChange(status), documentHref(id)
export default function DocumentList({ documents, loadFailed, filter, onFilterChange, documentHref }) {
  return (
    <div className="document-list">
      <div className="field field--inline">
        <label htmlFor="status-filter">Show status</label>
        <select
          id="status-filter"
          value={filter}
          onChange={(event) => onFilterChange(event.target.value)}
        >
          <option value="">All statuses</option>
          {STATUSES.map((status) => (
            <option key={status} value={status}>
              {STATUS_LABELS[status]}
            </option>
          ))}
        </select>
      </div>

      {loadFailed ? (
        <p>The document list could not be loaded.</p>
      ) : documents === null ? (
        <p>Loading documents…</p>
      ) : documents.length === 0 ? (
        <p>
          {filter
            ? `No documents with status “${STATUS_LABELS[filter]}”.`
            : 'No documents yet. Upload a PDF to start.'}
        </p>
      ) : (
        <div className="table-scroll">
          <table>
            <caption>
              {documents.length === 1 ? '1 document' : `${documents.length} documents`}
              {filter ? ` with status “${STATUS_LABELS[filter]}”` : ''}, newest first
            </caption>
            <thead>
              <tr>
                <th scope="col">File</th>
                <th scope="col">Status</th>
                <th scope="col">Open flags</th>
                <th scope="col">Uploaded</th>
              </tr>
            </thead>
            <tbody>
              {documents.map((doc) => (
                <tr key={doc.id}>
                  <th scope="row">
                    <a href={documentHref(doc.id)}>{doc.file_name}</a>
                  </th>
                  <td>
                    <StatusBadge status={doc.status} />
                    {doc.error_code ? <span className="code-note">{doc.error_code}</span> : null}
                  </td>
                  <td>{doc.status === 'failed' ? 'Not extracted' : doc.flag_count}</td>
                  <td>
                    <time dateTime={doc.created_at}>{formatTime(doc.created_at)}</time>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
