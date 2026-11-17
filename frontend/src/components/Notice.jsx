import { CheckIcon, ErrorIcon } from './icons.jsx'

// Two live regions that are always in the DOM (a region must exist before its
// text changes for screen readers to announce it). `notice` is
// { kind: 'success' | 'info' | 'error', text } or null.
export default function Notice({ notice }) {
  const isError = notice?.kind === 'error'
  return (
    <div className="notice-slot">
      <div role="status" className={notice && !isError ? `notice notice--${notice.kind}` : 'notice'}>
        {notice && !isError ? (
          <>
            {notice.kind === 'success' ? <CheckIcon /> : null}
            <span>{notice.text}</span>
          </>
        ) : null}
      </div>
      <div role="alert" className={isError ? 'notice notice--error' : 'notice'}>
        {isError ? (
          <>
            <ErrorIcon />
            <span>{notice.text}</span>
          </>
        ) : null}
      </div>
    </div>
  )
}
