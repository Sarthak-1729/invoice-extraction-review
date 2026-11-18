import { screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axeViolations } from '../test/a11y.js'
import { apiError, createFakeApi, deferred, failedDocument, flag, makeDocument, summary } from '../test/fakeApi.js'
import { liveRegions, renderApp } from '../test/render.jsx'

function seed() {
  return [
    makeDocument({ file_name: 'dev-01.pdf' }),
    makeDocument({
      file_name: 'dev-05.pdf',
      status: 'needs_review',
      flags: [flag('subtotal', 'TOTAL_MISMATCH'), flag('total', 'TOTAL_MISMATCH')],
    }),
    makeDocument({ file_name: 'dev-03.pdf', status: 'approved', approved_at: '2026-11-17T11:00:00+00:00' }),
    failedDocument(),
  ]
}

function documentsSection() {
  return screen.getByRole('region', { name: 'Documents' })
}

describe('document list', () => {
  it('shows every document with status as icon plus text, flag count and a link', async () => {
    const docs = seed()
    await renderApp(createFakeApi(docs))
    const table = await screen.findByRole('table', { name: /4 documents, newest first/ })
    const rows = within(table).getAllByRole('row').slice(1)
    const cells = rows.map((row) => within(row).getAllByRole('cell').map((c) => c.textContent))
    expect(rows.map((r) => within(r).getByRole('rowheader').textContent)).toEqual([
      'dev-01.pdf',
      'dev-05.pdf',
      'dev-03.pdf',
      'dev-07.pdf',
    ])
    expect(cells.map((c) => c[0])).toEqual([
      'Extracted',
      'Needs review',
      'Approved',
      'FailedLLM_RATE_LIMITED',
    ])
    expect(cells.map((c) => c[1])).toEqual(['0', '2', '0', 'Not extracted'])
    // Status is never color alone: an icon (hidden from screen readers) plus text.
    for (const row of rows) {
      const badge = row.querySelector('.status')
      expect(badge.querySelector('svg')).toHaveAttribute('aria-hidden', 'true')
      expect(badge.textContent.trim()).not.toBe('')
    }
    expect(within(table).getByRole('link', { name: 'dev-05.pdf' })).toHaveAttribute(
      'href',
      `#/documents/${docs[1].id}`,
    )
  })

  it('filters by status, asks the API for that status and announces the count', async () => {
    const api = createFakeApi(seed())
    const { user } = await renderApp(api)
    await screen.findByRole('table')
    await user.selectOptions(screen.getByLabelText('Show status'), 'Needs review')
    expect(api.listDocuments).toHaveBeenLastCalledWith('needs_review')
    const { status } = liveRegions(documentsSection())
    await waitFor(() => expect(status).toHaveTextContent('Showing 1 document with status “Needs review”.'))
    const table = screen.getByRole('table', { name: /1 document with status “Needs review”/ })
    expect(within(table).getAllByRole('rowheader').map((h) => h.textContent)).toEqual(['dev-05.pdf'])

    await user.selectOptions(screen.getByLabelText('Show status'), 'Approved')
    await waitFor(() => expect(status).toHaveTextContent('Showing 1 document with status “Approved”.'))

    await user.selectOptions(screen.getByLabelText('Show status'), 'All statuses')
    expect(api.listDocuments).toHaveBeenLastCalledWith(undefined)
    await waitFor(() => expect(status).toHaveTextContent('Showing 4 documents.'))
  })

  it('says when a filter matches nothing', async () => {
    const api = createFakeApi([makeDocument()])
    const { user } = await renderApp(api)
    await screen.findByRole('table')
    await user.selectOptions(screen.getByLabelText('Show status'), 'Failed')
    expect(await screen.findByText('No documents with status “Failed”.')).toBeInTheDocument()
  })

  it('ignores an older response that arrives after a newer one', async () => {
    const docs = seed()
    const api = createFakeApi(docs)
    const { user } = await renderApp(api)
    await screen.findByRole('table')
    const slow = deferred()
    const fast = deferred()
    api.listDocuments.mockImplementationOnce(() => slow.promise).mockImplementationOnce(() => fast.promise)

    await user.selectOptions(screen.getByLabelText('Show status'), 'Failed') // slow
    await user.selectOptions(screen.getByLabelText('Show status'), 'Approved') // fast
    fast.resolve([summary(docs[2])])
    await screen.findByRole('table', { name: /1 document with status “Approved”/ })
    slow.resolve([summary(docs[3])]) // the stale "Failed" answer arrives last
    await new Promise((r) => setTimeout(r, 20))

    const table = screen.getByRole('table')
    expect(within(table).getAllByRole('rowheader').map((h) => h.textContent)).toEqual(['dev-03.pdf'])
    expect(liveRegions(documentsSection()).status).toHaveTextContent('status “Approved”')
  })

  it('shows an empty list as empty, and a failed load as an error (not as empty)', async () => {
    await renderApp(createFakeApi([]))
    expect(await screen.findByText('No documents yet. Upload a PDF to start.')).toBeInTheDocument()
  })

  it('reports an unreachable API in the alert region', async () => {
    const api = createFakeApi()
    api.listDocuments.mockRejectedValue(apiError(0, 'NETWORK_ERROR', 'Could not reach the API.'))
    await renderApp(api)
    expect(await screen.findByText('The document list could not be loaded.')).toBeInTheDocument()
    expect(screen.queryByText(/No documents yet/)).not.toBeInTheDocument()
    expect(liveRegions(documentsSection()).alert).toHaveTextContent('Error code: NETWORK_ERROR.')
  })

  it('has landmarks, a skip link, ordered headings and no axe violations', async () => {
    await renderApp(createFakeApi(seed()))
    await screen.findByRole('table')
    expect(screen.getByRole('banner')).toBeInTheDocument()
    expect(screen.getByRole('main')).toHaveAttribute('id', 'main')
    expect(screen.getByRole('contentinfo')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Skip to main content' })).toHaveAttribute('href', '#main')
    const levels = screen.getAllByRole('heading').map((h) => Number(h.tagName[1]))
    expect(levels).toEqual([1, 2, 2, 2])
    expect(await axeViolations()).toEqual([])
  })

  it('skip link moves focus to main without changing the route', async () => {
    const { user } = await renderApp(createFakeApi([]))
    document.activeElement.blur() // start from the top of the page
    await user.tab()
    expect(screen.getByRole('link', { name: 'Skip to main content' })).toHaveFocus()
    await user.keyboard('{Enter}')
    expect(screen.getByRole('main')).toHaveFocus()
    expect(window.location.hash).toBe('#/')
  })
})
