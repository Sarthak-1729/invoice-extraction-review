import { screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axeViolations } from '../test/a11y.js'
import { apiError, createFakeApi, deferred, flag, makeDocument } from '../test/fakeApi.js'
import { liveRegions, renderApp } from '../test/render.jsx'

function flaggedDocument() {
  const doc = makeDocument({
    file_name: 'dev-03.pdf',
    status: 'needs_review',
    flags: [
      flag('currency', 'CURRENCY_AMBIGUOUS', 'warning', 'The currency symbol is used by several currencies.'),
      flag('line_items[0].amount', 'LINE_AMOUNT_MISMATCH', 'error', 'Quantity × unit price does not match.'),
    ],
  })
  doc.raw.currency = '$'
  doc.normalized.currency = null
  return doc
}

function describedText(element) {
  return element
    .getAttribute('aria-describedby')
    .split(' ')
    .map((id) => document.getElementById(id).textContent)
    .join(' | ')
}

function fieldsForm() {
  return screen.getByRole('form', { name: 'Invoice fields' })
}

describe('review screen', () => {
  it('shows the PDF in a titled frame with a new-tab fallback link', async () => {
    const doc = flaggedDocument()
    await renderApp(createFakeApi([doc]), `#/documents/${doc.id}`)
    expect(screen.getByTitle('PDF preview of dev-03.pdf')).toHaveAttribute(
      'src',
      `http://api.test/api/documents/${doc.id}/pdf`,
    )
    const link = screen.getByRole('link', { name: /Open PDF in new tab/ })
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
    await waitFor(() => expect(document.title).toBe('dev-03.pdf – Invoice review'))
  })

  it('labels every field and links flags and values with aria-describedby', async () => {
    const doc = flaggedDocument()
    await renderApp(createFakeApi([doc]), `#/documents/${doc.id}`)

    const currency = screen.getByRole('textbox', { name: /Currency/ })
    expect(currency).toHaveValue('$')
    expect(currency).toHaveAccessibleName('Currency Flagged')
    expect(describedText(currency)).toContain('Extracted text$')
    expect(describedText(currency)).toContain('Normalized(empty)')
    expect(describedText(currency)).toContain('Warning CURRENCY_AMBIGUOUS: The currency symbol')
    expect(currency).not.toHaveAttribute('aria-invalid') // a warning, not an error

    // Line-item inputs are named by their row and column headers.
    const amount = screen.getByRole('textbox', { name: 'Line 1 Amount' })
    expect(amount).toHaveValue('$100.00')
    expect(amount).toHaveAttribute('aria-invalid', 'true')
    expect(describedText(amount)).toContain('Error LINE_AMOUNT_MISMATCH: Quantity × unit price')
    expect(describedText(amount)).toContain('Normalized100.00')

    // Unflagged fields have no flag description and no "Flagged" marker.
    const total = screen.getByRole('textbox', { name: 'Total' })
    expect(total.getAttribute('aria-describedby')).toBe('field-total-values')

    // Every input has a visible label: header fields use <label>, table
    // inputs use the visible row and column headers.
    for (const input of within(fieldsForm()).getAllByRole('textbox')) {
      expect(input).toHaveAccessibleName()
    }
    const table = screen.getByRole('table', { name: /1 line item/ })
    expect(within(table).getAllByRole('columnheader').map((h) => h.textContent)).toEqual([
      'Line',
      'Description',
      'Quantity',
      'Unit price',
      'Amount',
    ])
    expect(within(table).getByRole('rowheader', { name: 'Line 1' })).toBeInTheDocument()
  })

  it('lists open flags with a button that moves focus to the field', async () => {
    const doc = flaggedDocument()
    const { user } = await renderApp(createFakeApi([doc]), `#/documents/${doc.id}`)
    const summary = screen.getByRole('region', { name: '2 open flags' })
    expect(summary).toHaveTextContent('Warning in Currency: CURRENCY_AMBIGUOUS')
    expect(summary).toHaveTextContent('Error in Line 1, amount: LINE_AMOUNT_MISMATCH')
    await user.click(within(summary).getByRole('button', { name: 'Go to line 1, amount' }))
    expect(screen.getByRole('textbox', { name: 'Line 1 Amount' })).toHaveFocus()
    await user.click(within(summary).getByRole('button', { name: 'Go to currency' }))
    expect(screen.getByRole('textbox', { name: /Currency/ })).toHaveFocus()
  })

  it('saves edits with one PATCH and announces the new status and flags', async () => {
    const doc = flaggedDocument()
    const api = createFakeApi([doc])
    const pending = deferred()
    api.updateFields.mockImplementation(async (id, changes) => {
      await pending.promise
      return {
        ...doc,
        status: 'needs_review',
        raw: { ...doc.raw, currency: 'USD' },
        normalized: { ...doc.normalized, currency: 'USD' },
        flags: [doc.flags[1]],
        flag_count: 1,
        corrected_paths: ['currency'],
        corrections: changes.map((c) => ({
          field_path: c.field_path,
          original_value: '$',
          corrected_value: c.value,
          created_at: '2026-11-17T12:00:00+00:00',
        })),
      }
    })
    const { user } = await renderApp(api, `#/documents/${doc.id}`)
    const currency = screen.getByRole('textbox', { name: /Currency/ })
    await user.clear(currency)
    await user.type(currency, 'USD')
    expect(screen.getByText('1 unsaved edit.')).toBeInTheDocument()
    await user.keyboard('{Enter}') // submits the form from the field

    const { status, alert } = liveRegions(fieldsForm())
    expect(status).toHaveTextContent('Working…')
    pending.resolve()
    await waitFor(() =>
      expect(status).toHaveTextContent('Saved 1 change. Status: Needs review, 1 open flag.'),
    )
    expect(alert).toBeEmptyDOMElement()
    expect(api.updateFields).toHaveBeenCalledWith(doc.id, [{ field_path: 'currency', value: 'USD' }])
    expect(currency).toHaveFocus() // focus stays where the user was
    expect(currency).toHaveAccessibleName('Currency') // flag gone
    expect(describedText(currency)).toContain('SourceCorrected by reviewer')
    expect(screen.getByRole('region', { name: '1 open flag' })).toBeInTheDocument()
    expect(screen.getByText('No unsaved edits.')).toBeInTheDocument()

    const history = screen.getByRole('table', { name: /1 correction/ })
    const cells = within(history).getAllByRole('cell').map((c) => c.textContent)
    expect(within(history).getByRole('rowheader')).toHaveTextContent('Currency')
    expect(cells.slice(0, 2)).toEqual(['$', 'USD'])
    expect(within(history).getByRole('columnheader', { name: 'Time' })).toBeInTheDocument()
  })

  it('sends a cleared field as null and undoes unsaved edits', async () => {
    const doc = flaggedDocument()
    const api = createFakeApi([doc])
    const { user } = await renderApp(api, `#/documents/${doc.id}`)
    const vendor = screen.getByRole('textbox', { name: 'Vendor name' })
    await user.clear(vendor)
    await user.click(screen.getByRole('button', { name: 'Undo unsaved edits' }))
    expect(vendor).toHaveValue('Pellucia Works LLC')
    expect(api.updateFields).not.toHaveBeenCalled()

    await user.clear(vendor)
    await user.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(api.updateFields).toHaveBeenCalledWith(doc.id, [{ field_path: 'vendor_name', value: null }])
  })

  it('does not call the API when nothing changed', async () => {
    const doc = flaggedDocument()
    const api = createFakeApi([doc])
    const { user } = await renderApp(api, `#/documents/${doc.id}`)
    await user.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(liveRegions(fieldsForm()).status).toHaveTextContent('No changes to save.')
    expect(api.updateFields).not.toHaveBeenCalled()
  })

  it('announces a rejected save in the alert region and keeps the edit', async () => {
    const doc = flaggedDocument()
    const api = createFakeApi([doc])
    api.updateFields.mockRejectedValueOnce(apiError(422, 'INVALID_VALUE', 'Value too long'))
    const { user } = await renderApp(api, `#/documents/${doc.id}`)
    const currency = screen.getByRole('textbox', { name: /Currency/ })
    await user.clear(currency)
    await user.type(currency, 'XYZ{Enter}')
    const { alert } = liveRegions(fieldsForm())
    await waitFor(() => expect(alert).toHaveTextContent('One of the values is not valid. (Value too long)'))
    expect(alert).toHaveTextContent('Error code: INVALID_VALUE.')
    expect(currency).toHaveValue('XYZ')
  })

  it('keeps focus on Save while the request is running', async () => {
    const doc = flaggedDocument()
    const api = createFakeApi([doc])
    const pending = deferred()
    api.updateFields.mockImplementation(() => pending.promise)
    const { user } = await renderApp(api, `#/documents/${doc.id}`)
    await user.type(screen.getByRole('textbox', { name: 'Tax' }), '0')
    const save = screen.getByRole('button', { name: 'Save changes' })
    await user.click(save)
    expect(save).toHaveFocus()
    expect(save).toHaveAttribute('aria-disabled', 'true')
    await user.click(save) // ignored while busy
    expect(api.updateFields).toHaveBeenCalledTimes(1)
    pending.resolve(doc)
    await waitFor(() => expect(save).not.toHaveAttribute('aria-disabled'))
  })

  it('shows a clear message for an unknown document id', async () => {
    window.location.hash = '#/documents/doesnotexist'
    const api = createFakeApi([])
    const { render } = await import('@testing-library/react')
    const App = (await import('../App.jsx')).default
    render(<App api={api} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Error code: NOT_FOUND.')
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Document not available')
  })

  it('has no axe violations with open flags', async () => {
    const doc = flaggedDocument()
    await renderApp(createFakeApi([doc]), `#/documents/${doc.id}`)
    const levels = screen.getAllByRole('heading').map((h) => Number(h.tagName[1]))
    expect(levels).toEqual([1, 2, 2, 2, 3, 3, 2, 2])
    expect(await axeViolations()).toEqual([])
  })
})
