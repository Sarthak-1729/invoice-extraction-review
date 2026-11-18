import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from '../App.jsx'

// Renders the whole app with a fake api at a given hash route.
export async function renderApp(api, hash = '#/', userOptions = {}) {
  window.location.hash = hash
  const user = userEvent.setup(userOptions)
  const view = render(<App api={api} />)
  if (hash.startsWith('#/documents/')) {
    await screen.findByRole('heading', { level: 2, name: /original pdf/i })
  } else {
    await screen.findByRole('heading', { level: 1, name: 'Invoices' })
  }
  return { user, ...view }
}

export function pdfFile(name = 'dev-05.pdf') {
  return new File(['%PDF-1.4 synthetic'], name, { type: 'application/pdf' })
}

// The status (polite) and alert (assertive) live regions inside a section.
export function liveRegions(container) {
  return {
    status: container.querySelector('[role=status]'),
    alert: container.querySelector('[role=alert]'),
  }
}
