import FieldsForm from './FieldsForm.jsx'
import { ApprovePanel, CorrectionsTable, FailedPanel, FlagSummary, PdfViewer } from './ReviewParts.jsx'
import StatusBadge from './StatusBadge.jsx'

// Presentational: everything comes in as props.
//   notices: { fields, approve, failed } each { kind, text } | null
//   on: { save(changes), approve(ack), retry(), delete(), dirtyChange(bool), approveError(text) }
export default function ReviewScreen({ document, pdfUrl, busy, dirty, notices, on }) {
  const failed = document.status === 'failed'
  const locked = document.status === 'approved'
  return (
    <div className="review">
      <p className="review-meta">
        <StatusBadge status={document.status} />
        <span>
          {document.page_count === 1 ? '1 page' : `${document.page_count} pages`}
          {document.model ? ` · extracted by ${document.provider} / ${document.model}` : ''}
          {document.prompt_version ? ` · prompt ${document.prompt_version}` : ''}
        </span>
      </p>
      <div className="review-layout">
        <PdfViewer url={pdfUrl} fileName={document.file_name} />
        <div className="review-fields">
          {failed ? (
            <FailedPanel
              document={document}
              busy={busy}
              notice={notices.failed}
              onRetry={on.retry}
              onDelete={on.delete}
            />
          ) : (
            <>
              <FlagSummary flags={document.flags} />
              <FieldsForm
                document={document}
                locked={locked}
                busy={busy}
                notice={notices.fields}
                onSave={on.save}
                onDirtyChange={on.dirtyChange}
              />
              <ApprovePanel
                document={document}
                dirty={dirty}
                busy={busy}
                notice={notices.approve}
                onApprove={on.approve}
                onError={on.approveError}
              />
              <CorrectionsTable corrections={document.corrections || []} />
            </>
          )}
        </div>
      </div>
    </div>
  )
}
