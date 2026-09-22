import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { GMeetRecordPage } from '@/pages/GMeetRecordPage'

describe('GMeetRecordPage', () => {
  it('explains how to share a Meet tab before a session exists', () => {
    render(
      <MemoryRouter>
        <GMeetRecordPage />
      </MemoryRouter>,
    )

    expect(screen.getByText('Record Google Meet')).toBeInTheDocument()
    expect(screen.getByText(/Share tab audio/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Create session/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Share Meet tab/i })).not.toBeInTheDocument()
  })
})
