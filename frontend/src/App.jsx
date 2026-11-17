import { useState, useSyncExternalStore } from 'react'
import ListPage from './pages/ListPage.jsx'
import ReviewPage from './pages/ReviewPage.jsx'

// Hash routes: "#/" is the list, "#/documents/<id>" the review screen.
// Focus moves to the page heading only after a navigation, not on first load.
let navigated = false

function subscribe(callback) {
  const handler = () => {
    navigated = true
    callback()
  }
  window.addEventListener('hashchange', handler)
  return () => window.removeEventListener('hashchange', handler)
}

function parseRoute(hash) {
  const match = /^#\/documents\/([A-Za-z0-9]{1,64})$/.exec(hash)
  return match ? { page: 'review', id: match[1] } : { page: 'list' }
}

const documentHref = (id) => `#/documents/${id}`
const LIST_HREF = '#/'

// `api` is passed in (see main.jsx), so tests can inject a fake.
export default function App({ api }) {
  const hash = useSyncExternalStore(subscribe, () => window.location.hash)
  const route = parseRoute(hash)
  const [flash, setFlash] = useState(null)
  if (flash && route.page === 'review') setFlash(null) // shown once, on the list

  function handleDeleted(message) {
    setFlash(message)
    window.location.hash = LIST_HREF
  }

  return (
    <>
      <a className="skip-link" href="#main" onClick={(event) => {
        event.preventDefault()
        window.document.getElementById('main')?.focus()
      }}>
        Skip to main content
      </a>
      <header className="site-header">
        <a className="site-title" href={LIST_HREF}>
          Invoice extraction review
        </a>
      </header>
      <main id="main" tabIndex={-1}>
        {route.page === 'review' ? (
          <ReviewPage
            key={route.id}
            api={api}
            id={route.id}
            focusHeading={navigated}
            onDeleted={handleDeleted}
            listHref={LIST_HREF}
          />
        ) : (
          <ListPage
            key={flash || 'list'}
            api={api}
            focusHeading={navigated}
            flash={flash}
            documentHref={documentHref}
          />
        )}
      </main>
      <footer className="site-footer">
        <p>Synthetic invoices only. Extracted values are checked by rules, never by model confidence.</p>
      </footer>
    </>
  )
}
