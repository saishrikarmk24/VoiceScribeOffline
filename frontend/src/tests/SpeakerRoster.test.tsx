import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { SpeakerRoster } from '@/components/session/SpeakerRoster'
import { api } from '@/services/api'

import { speakers } from './fixtures'

describe('SpeakerRoster', () => {
  it('shows the diarized label and the auto-assigned role', () => {
    render(<SpeakerRoster speakers={speakers} />)
    expect(screen.getByText('Speaker 1')).toBeInTheDocument()
    expect(screen.getByText('Detected Doctor')).toBeInTheDocument()
    expect(screen.getByText('Detected Patient')).toBeInTheDocument()
  })

  it('sends a human role override to the backend', async () => {
    const updated = { ...speakers[0], role: 'NURSE' as const, role_source: 'HUMAN' }
    const spy = vi.spyOn(api, 'updateSpeakerRole').mockResolvedValue(updated)
    const onChanged = vi.fn()

    render(<SpeakerRoster speakers={speakers} editable={true} onChanged={onChanged} />)
    await userEvent.selectOptions(screen.getByLabelText('Role for speaker_0'), 'NURSE')

    await waitFor(() => expect(spy).toHaveBeenCalledWith('sp-0', 'NURSE'))
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(updated))
  })

  it('renders read-only badges when editing is disabled', () => {
    render(<SpeakerRoster speakers={speakers} editable={false} />)
    expect(screen.queryByLabelText('Role for speaker_0')).not.toBeInTheDocument()
    expect(screen.getByText('Doctor')).toBeInTheDocument()
  })
})
