import { screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { apiError, createFakeApi, deferred, failedDocument, flag, makeDocument } from '../test/fakeApi.js'
import { liveRegions, pdfFile, renderApp } from '../test/render.jsx'

function uploadSection() {
  return screen.getByRole('region', { name: 'Upload a PDF' })
}

async function chooseAndUpload(user, file = pdfFile()) {
  await user.upload(screen.getByLabelText('PDF file'), file)
  await user.click(screen.getByRole('button', { name: 'Upload and extract' }))
}

describe('upload', () => {
  it('shows upload progress, then extraction, then the result with a review link', async () => {
    const api = createFakeApi()
    const progress = deferred()
    const extraction = deferred()
    api.uploadDocument.mockImplementation(async (file, onProgress) => {
      onProgress({ loaded: 30, total: 100 })
      await progress.promise
      onProgress({ done: true })
      await extraction.promise
      const doc = makeDocument({
        file_name: file.name,
        status: 'needs_review',
        flags: [flag('total', 'TOTAL_MISMATCH')],
      })
      api.store.set(doc.id, doc)
      return { document: doc, duplicateOfFailed: false }
    })
    const { user } = await renderApp(api)
    await chooseAndUpload(user)
    const { status } = liveRegions(uploadSection())

    expect(await screen.findByRole('progressbar', { name: 'Upload progress' })).toHaveValue(30)
    expect(status).toHaveTextContent('Uploading dev-05.pdf…')

    progress.resolve()
    expect(await screen.findByRole('progressbar', { name: 'Extraction in progress' })).toBeInTheDocument()
    expect(status).toHaveTextContent('Upload complete. Extracting fields from dev-05.pdf')

    extraction.resolve()
    await waitFor(() => expect(status).toHaveTextContent('dev-05.pdf: Needs review, 1 open flag.'))
    expect(within(uploadSection()).getByRole('link', { name: 'Review dev-05.pdf' })).toHaveAttribute(
      'href',
      expect.stringMatching(/^#\/documents\//),
    )
    // The list is refreshed and shows the new row.
    const table = await screen.findByRole('table', { name: /1 document/ })
    expect(within(table).getByRole('link', { name: 'dev-05.pdf' })).toBeInTheDocument()
    expect(api.uploadDocument).toHaveBeenCalledTimes(1)
    expect(api.uploadDocument.mock.calls[0][0].name).toBe('dev-05.pdf')
  })

  it('asks for a file when none is chosen and moves focus to the picker', async () => {
    const api = createFakeApi()
    const { user } = await renderApp(api)
    await user.click(screen.getByRole('button', { name: 'Upload and extract' }))
    expect(liveRegions(uploadSection()).alert).toHaveTextContent('Choose a PDF file first.')
    expect(screen.getByLabelText('PDF file')).toHaveFocus()
    expect(api.uploadDocument).not.toHaveBeenCalled()
  })

  it.each([
    [409, 'DUPLICATE', 'This PDF was already uploaded.'],
    [413, 'FILE_TOO_LARGE', 'The file is larger than the upload limit.'],
    [415, 'NOT_A_PDF', 'This file is not a PDF.'],
    [422, 'SCANNED_PDF_UNSUPPORTED', 'This PDF has no text layer (it looks scanned).'],
    [422, 'ENCRYPTED_PDF', 'This PDF is password-protected.'],
    [422, 'TOO_MANY_PAGES', 'This PDF has more pages than the limit.'],
    [422, 'INVALID_PDF', 'This PDF could not be read.'],
    [403, 'TEST_SET_DOCUMENT', 'This PDF is part of the frozen evaluation test set'],
    [502, 'LLM_UNAVAILABLE', 'The extraction service is unavailable right now.'],
    [502, 'HTTP_502', 'HTTP_502 from server'],
    [0, 'NETWORK_ERROR', 'The API could not be reached.'],
  ])('%i %s shows a clear message with the error code', async (status, code, text) => {
    const api = createFakeApi()
    api.uploadDocument.mockRejectedValueOnce(apiError(status, code))
    const { user } = await renderApp(api)
    await chooseAndUpload(user)
    const { alert } = liveRegions(uploadSection())
    await waitFor(() => expect(alert).toHaveTextContent(text))
    expect(alert).toHaveTextContent(`Error code: ${code}.`)
  })

  it('links a duplicate to the existing document', async () => {
    const api = createFakeApi()
    api.uploadDocument.mockRejectedValueOnce(
      apiError(409, 'DUPLICATE', 'This PDF was already uploaded.', { document_id: 'abc123' }),
    )
    const { user } = await renderApp(api)
    await chooseAndUpload(user)
    expect(
      await within(uploadSection()).findByRole('link', { name: 'Open the existing document' }),
    ).toHaveAttribute('href', '#/documents/abc123')
  })

  it('shows a failed extraction from a new upload with Retry', async () => {
    const api = createFakeApi()
    const failed = failedDocument({ error_code: 'LLM_TIMEOUT', error: { code: 'LLM_TIMEOUT', message: 'timed out' } })
    api.uploadDocument.mockResolvedValueOnce({ document: failed, duplicateOfFailed: false })
    const { user } = await renderApp(api)
    await chooseAndUpload(user, pdfFile('dev-07.pdf'))
    const { alert } = liveRegions(uploadSection())
    await waitFor(() => expect(alert).toHaveTextContent('dev-07.pdf was saved, but extraction failed.'))
    expect(alert).toHaveTextContent('Error code: LLM_TIMEOUT.')
  })

  it('shows the existing failed document for a duplicate upload, and Retry extracts it', async () => {
    const failed = failedDocument()
    const api = createFakeApi([failed])
    api.uploadDocument.mockResolvedValueOnce({ document: failed, duplicateOfFailed: true })
    const { user } = await renderApp(api)
    await chooseAndUpload(user, pdfFile('dev-07.pdf'))
    const section = uploadSection()
    const { alert, status } = liveRegions(section)
    await waitFor(() =>
      expect(alert).toHaveTextContent('dev-07.pdf was uploaded before and its extraction failed.'),
    )
    expect(alert).toHaveTextContent('The extraction service is rate-limited.')
    expect(within(section).getByRole('link', { name: 'Open dev-07.pdf' })).toHaveAttribute(
      'href',
      `#/documents/${failed.id}`,
    )

    await user.click(within(section).getByRole('button', { name: 'Retry extraction' }))
    expect(api.retryExtraction).toHaveBeenCalledWith(failed.id)
    await waitFor(() =>
      expect(status).toHaveTextContent('dev-07.pdf extracted after retry: Extracted, 0 open flags.'),
    )
    expect(alert).toBeEmptyDOMElement()
  })
})
