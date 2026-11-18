import { screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axeViolations } from '../test/a11y.js'
import { apiError, createFakeApi, flag, makeDocument } from '../test/fakeApi.js'
import { liveRegions, renderApp } from '../test/render.jsx'

function withFlags() {
  return makeDocument({
    file_name: 'dev-05.pdf',
    status: 'needs_review',
    flags: [
      flag('subtotal', 'SUBTOTAL_MISMATCH'),
      flag('line_items', 'SUBTOTAL_MISMATCH'),
      flag('total', 'TOTAL_MISMATCH'),
    ],
  })
}

function approveSection() {
  return screen.getByRole('region', { name: /^Approve/ })
}

describe('approve', () => {
  it('approves a document without flags, then shows it locked and read-only', async () => {
    const doc = makeDocument()
    const api = createFakeApi([doc])
    const { user } = await renderApp(api, `#/documents/${doc.id}`)
    expect(within(approveSection()).queryByRole('checkbox')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Approve document' }))

    expect(api.approve).toHaveBeenCalledWith(doc.id, false)
    const heading = await screen.findByRole('heading', { level: 2, name: 'Approved' })
    expect(heading).toHaveFocus() // the Approve button is gone; focus is not lost
    expect(liveRegions(approveSection()).status).toHaveTextContent(
      'Approved. The document is now locked and included in exports.',
    )
    expect(approveSection()).toHaveTextContent('Approved on')
    for (const input of screen.getAllByRole('textbox')) expect(input).toHaveAttribute('readonly')
    expect(screen.queryByRole('button', { name: 'Save changes' })).not.toBeInTheDocument()
    expect(screen.getByText('This document is approved, so its fields are read-only.')).toBeInTheDocument()
    // The status badge at the top says Approved as text.
    expect(document.querySelector('.review-meta .status')).toHaveTextContent('Approved')
  })

  it('with open flags, refuses until the confirmation box is ticked and moves focus to it', async () => {
    const doc = withFlags()
    const api = createFakeApi([doc])
    const { user } = await renderApp(api, `#/documents/${doc.id}`)
    const section = approveSection()
    expect(section).toHaveTextContent('3 flags are still open.')
    const checkbox = within(section).getByRole('checkbox', {
      name: 'I checked the open flags against the PDF and approve anyway.',
    })
    expect(checkbox).toHaveAccessibleDescription(/3 flags are still open/)
    expect(checkbox).not.toBeChecked()

    await user.click(within(section).getByRole('button', { name: 'Approve document' }))
    expect(api.approve).not.toHaveBeenCalled()
    expect(liveRegions(section).alert).toHaveTextContent(
      'Tick the confirmation box to approve a document with open flags.',
    )
    expect(checkbox).toHaveFocus()

    await user.keyboard(' ') // tick with the keyboard
    expect(checkbox).toBeChecked()
    await user.tab()
    expect(within(section).getByRole('button', { name: 'Approve document' })).toHaveFocus()
    await user.keyboard('{Enter}')

    expect(api.approve).toHaveBeenCalledWith(doc.id, true)
    const approved = await screen.findByRole('region', { name: /^Approved/ })
    expect(approved).toHaveTextContent('The reviewer approved it with 3 open flags acknowledged.')
    expect(screen.getByRole('heading', { level: 2, name: 'Approved' })).toHaveFocus()
  })

  it('names the flagged line-item table "Line items Flagged"', async () => {
    const doc = withFlags()
    await renderApp(createFakeApi([doc]), `#/documents/${doc.id}`)
    expect(screen.getByRole('heading', { level: 3, name: 'Line items Flagged' })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: /1 line item/ })).toHaveAccessibleDescription(
      /SUBTOTAL_MISMATCH/,
    )
  })

  it('will not approve while edits are unsaved', async () => {
    const doc = makeDocument()
    const api = createFakeApi([doc])
    const { user } = await renderApp(api, `#/documents/${doc.id}`)
    await user.type(screen.getByRole('textbox', { name: 'Tax' }), '9')
    await user.click(screen.getByRole('button', { name: 'Approve document' }))
    expect(api.approve).not.toHaveBeenCalled()
    expect(liveRegions(approveSection()).alert).toHaveTextContent(
      'Save or undo your edits before approving.',
    )
  })

  it('shows a server refusal in the alert region', async () => {
    const doc = makeDocument()
    const api = createFakeApi([doc])
    api.approve.mockRejectedValueOnce(apiError(409, 'OPEN_FLAGS', 'Flags are open.'))
    const { user } = await renderApp(api, `#/documents/${doc.id}`)
    await user.click(screen.getByRole('button', { name: 'Approve document' }))
    await waitFor(() =>
      expect(liveRegions(approveSection()).alert).toHaveTextContent(
        'This document still has open flags. (Flags are open.) Error code: OPEN_FLAGS.',
      ),
    )
  })

  it('opens an approved document read-only with a visible Approved state and no axe violations', async () => {
    const doc = makeDocument({
      status: 'approved',
      approved_at: '2026-11-17T11:00:00+00:00',
      corrections: [
        {
          field_path: 'line_items[0].description',
          original_value: 'Server monitorng',
          corrected_value: 'Server monitoring',
          created_at: '2026-11-17T10:30:00+00:00',
        },
      ],
    })
    await renderApp(createFakeApi([doc]), `#/documents/${doc.id}`)
    expect(screen.getByRole('heading', { level: 2, name: 'Approved' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Approve document' })).not.toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Total' })).toHaveAttribute('readonly')
    const history = screen.getByRole('table', { name: /1 correction/ })
    expect(within(history).getByRole('rowheader')).toHaveTextContent('Line 1, description')
    expect(within(history).getByText('Server monitorng')).toBeInTheDocument()
    expect(history.querySelector('time')).toHaveAttribute('datetime', '2026-11-17T10:30:00+00:00')
    expect(await axeViolations()).toEqual([])
  })
})
