import { screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { apiError, createFakeApi } from '../test/fakeApi.js'
import { liveRegions, renderApp } from '../test/render.jsx'

const ID_A = 'a'.repeat(32)
const ID_B = 'b'.repeat(32)
const CSV_HEADER = 'document_id,file_name,approved_at,invoice_number\n'

function exportSection() {
  return screen.getByRole('region', { name: 'Export' })
}

// jsdom has no object URLs or downloads: record what would be saved.
function captureDownloads() {
  const saved = []
  vi.stubGlobal('URL', { ...URL, createObjectURL: vi.fn(() => 'blob:test'), revokeObjectURL: vi.fn() })
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function click() {
    saved.push(this.download)
  })
  return saved
}

describe('export', () => {
  it('says nothing is approved yet and saves no file', async () => {
    const saved = captureDownloads()
    const api = createFakeApi()
    api.exportText.mockImplementation(async (format) =>
      format === 'json' ? JSON.stringify({ documents: [] }) : CSV_HEADER,
    )
    const { user } = await renderApp(api)
    for (const name of ['Download JSON', 'Download CSV']) {
      await user.click(screen.getByRole('button', { name }))
      await waitFor(() =>
        expect(liveRegions(exportSection()).status).toHaveTextContent(
          'Nothing to export yet: no document is approved.',
        ),
      )
    }
    expect(api.exportText.mock.calls).toEqual([['json'], ['csv']])
    expect(saved).toEqual([])
  })

  it('saves JSON and CSV and counts approved documents, not CSV rows', async () => {
    const saved = captureDownloads()
    const api = createFakeApi()
    api.exportText.mockImplementation(async (format) =>
      format === 'json'
        ? JSON.stringify({ documents: [{ document_id: ID_A }, { document_id: ID_B }] })
        : // two line items for A (one has a quoted newline), one for B
          `${CSV_HEADER}${ID_A},a.pdf,t,"line one\nline two"\n${ID_A},a.pdf,t,x\n${ID_B},b.pdf,t,y\n`,
    )
    const { user } = await renderApp(api)
    const { status } = liveRegions(exportSection())
    await user.click(screen.getByRole('button', { name: 'Download JSON' }))
    await waitFor(() => expect(status).toHaveTextContent('Saved invoices.json with 2 approved documents.'))
    await user.click(screen.getByRole('button', { name: 'Download CSV' }))
    await waitFor(() => expect(status).toHaveTextContent('Saved invoices.csv with 2 approved documents.'))
    expect(saved).toEqual(['invoices.json', 'invoices.csv'])
  })

  it('announces an export error', async () => {
    captureDownloads()
    const api = createFakeApi()
    api.exportText.mockRejectedValueOnce(apiError(0, 'NETWORK_ERROR', 'Could not reach the API.'))
    const { user } = await renderApp(api)
    await user.click(screen.getByRole('button', { name: 'Download CSV' }))
    await waitFor(() =>
      expect(liveRegions(exportSection()).alert).toHaveTextContent('Error code: NETWORK_ERROR.'),
    )
  })
})
