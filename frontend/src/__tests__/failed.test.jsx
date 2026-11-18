import { screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axeViolations } from '../test/a11y.js'
import { apiError, createFakeApi, deferred, failedDocument, flag, makeDocument } from '../test/fakeApi.js'
import { liveRegions, renderApp } from '../test/render.jsx'

function failedSection() {
  return screen.getByRole('region', { name: 'Extraction failed' })
}

describe('failed documents', () => {
  it('shows the error code and message with Retry and Delete, and no fields', async () => {
    const doc = failedDocument()
    await renderApp(createFakeApi([doc]), `#/documents/${doc.id}`)
    const section = failedSection()
    expect(section).toHaveTextContent('The extraction service is rate-limited. Wait a minute, then retry.')
    expect(section).toHaveTextContent('Error codeLLM_RATE_LIMITED')
    expect(section).toHaveTextContent('Server message429 RESOURCE_EXHAUSTED')
    expect(within(section).getByRole('button', { name: 'Retry extraction' })).toBeInTheDocument()
    expect(within(section).getByRole('button', { name: 'Delete' })).toBeInTheDocument()
    expect(screen.queryByRole('form', { name: 'Invoice fields' })).not.toBeInTheDocument()
    expect(document.querySelector('.review-meta .status')).toHaveTextContent('Failed')
    expect(await axeViolations()).toEqual([])
  })

  it('retry that fails again keeps focus on Retry and announces the error', async () => {
    const doc = failedDocument()
    const api = createFakeApi([doc])
    const pending = deferred()
    api.retryExtraction.mockImplementation(() => pending.promise)
    const { user } = await renderApp(api, `#/documents/${doc.id}`)
    const retry = screen.getByRole('button', { name: 'Retry extraction' })
    await user.click(retry)
    expect(retry).toHaveFocus()
    expect(retry).toHaveAttribute('aria-disabled', 'true')
    pending.resolve(failedDocument({ id: doc.id, error: { code: 'LLM_RATE_LIMITED', message: 'still 429' } }))
    await waitFor(() =>
      expect(liveRegions(failedSection()).alert).toHaveTextContent(
        'The extraction service is rate-limited. Wait a minute, then retry. (still 429) Error code: LLM_RATE_LIMITED.',
      ),
    )
    expect(retry).toHaveFocus()
    expect(api.retryExtraction).toHaveBeenCalledWith(doc.id)
  })

  it('retry that succeeds shows the fields and moves focus to the page heading', async () => {
    const doc = failedDocument()
    const api = createFakeApi([doc])
    api.retryExtraction.mockResolvedValueOnce(
      makeDocument({ id: doc.id, file_name: 'dev-07.pdf', status: 'needs_review', flags: [flag('total', 'TOTAL_MISMATCH')] }),
    )
    const { user } = await renderApp(api, `#/documents/${doc.id}`)
    await user.click(screen.getByRole('button', { name: 'Retry extraction' }))
    expect(await screen.findByRole('form', { name: 'Invoice fields' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1 })).toHaveFocus()
    expect(screen.getByRole('region', { name: '1 open flag' })).toBeInTheDocument()
  })

  it('delete asks for confirmation; Cancel returns focus to Delete', async () => {
    const doc = failedDocument()
    const api = createFakeApi([doc])
    const { user } = await renderApp(api, `#/documents/${doc.id}`)
    await user.click(screen.getByRole('button', { name: 'Delete' }))
    const confirm = screen.getByRole('group', { name: /Delete dev-07.pdf and its stored PDF\?/ })
    expect(confirm).toHaveTextContent('This cannot be undone.')
    const cancel = within(confirm).getByRole('button', { name: 'Cancel' })
    expect(cancel).toHaveFocus() // the safe choice gets focus
    await user.keyboard('{Enter}')
    expect(screen.queryByRole('group')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Delete' })).toHaveFocus()
    expect(api.deleteDocument).not.toHaveBeenCalled()
  })

  it('confirmed delete removes the document and returns to the list with a message', async () => {
    const doc = failedDocument()
    const other = makeDocument({ file_name: 'dev-01.pdf' })
    const api = createFakeApi([doc, other])
    const { user } = await renderApp(api, `#/documents/${doc.id}`)
    await user.click(screen.getByRole('button', { name: 'Delete' }))
    await user.click(screen.getByRole('button', { name: 'Yes, delete it' }))
    expect(api.deleteDocument).toHaveBeenCalledWith(doc.id)
    const heading = await screen.findByRole('heading', { level: 1, name: 'Invoices' })
    expect(window.location.hash).toBe('#/')
    expect(heading).toHaveFocus()
    const documents = screen.getByRole('region', { name: 'Documents' })
    expect(liveRegions(documents).status).toHaveTextContent('Deleted dev-07.pdf.')
    const table = await screen.findByRole('table')
    expect(within(table).getAllByRole('rowheader').map((h) => h.textContent)).toEqual(['dev-01.pdf'])
  })

  it('a failed delete stays on the page and announces the error', async () => {
    const doc = failedDocument()
    const api = createFakeApi([doc])
    api.deleteDocument.mockRejectedValueOnce(apiError(0, 'NETWORK_ERROR', 'Could not reach the API.'))
    const { user } = await renderApp(api, `#/documents/${doc.id}`)
    await user.click(screen.getByRole('button', { name: 'Delete' }))
    await user.click(screen.getByRole('button', { name: 'Yes, delete it' }))
    await waitFor(() =>
      expect(liveRegions(failedSection()).alert).toHaveTextContent('Error code: NETWORK_ERROR.'),
    )
    expect(window.location.hash).toBe(`#/documents/${doc.id}`)
  })
})
