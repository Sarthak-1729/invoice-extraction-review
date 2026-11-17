import { STATUS_LABELS } from '../labels.js'
import { AlertIcon, CheckIcon, ErrorIcon, LockIcon } from './icons.jsx'

const ICONS = {
  extracted: CheckIcon,
  needs_review: AlertIcon,
  approved: LockIcon,
  failed: ErrorIcon,
}

// Status as icon + text, never color alone.
export default function StatusBadge({ status }) {
  const IconFor = ICONS[status] || AlertIcon
  return (
    <span className={`status status--${status}`}>
      <IconFor />
      <span>{STATUS_LABELS[status] || status}</span>
    </span>
  )
}
