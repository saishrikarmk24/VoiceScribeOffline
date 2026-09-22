import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { TranscriptPanel } from '@/components/session/TranscriptPanel'

import { evidence, segments, speakers } from './fixtures'

describe('TranscriptPanel', () => {
  it('renders speaker role, timestamp, and text for every segment', () => {
    render(
      <TranscriptPanel
        segments={segments}
        speakers={speakers}
        evidence={evidence}
        selectedRef={null}
        highlightedRefs={[]}
        live
        onSelect={() => {}}
      />,
    )

    expect(screen.getByText('Good morning. What brings you in today?')).toBeInTheDocument()
    expect(screen.getByText("I've been having chest discomfort since yesterday evening.")).toBeInTheDocument()
    expect(screen.getAllByText('Speaker 1 (Doctor)')).toHaveLength(1)
    expect(screen.getAllByText('Speaker 2 (Patient)')).toHaveLength(2)
    expect(screen.getByText('00:00:00')).toBeInTheDocument()
    expect(screen.getByText('Live')).toBeInTheDocument()
  })

  it('marks segments that clinical statements cite', () => {
    render(
      <TranscriptPanel
        segments={segments}
        speakers={speakers}
        evidence={evidence}
        selectedRef={null}
        highlightedRefs={[]}
        live={false}
        onSelect={() => {}}
      />,
    )
    expect(screen.getByText('1 cited')).toBeInTheDocument()
  })

  it('selects a segment when clicked so the evidence panel can follow', async () => {
    const onSelect = vi.fn()
    render(
      <TranscriptPanel
        segments={segments}
        speakers={speakers}
        evidence={evidence}
        selectedRef={null}
        highlightedRefs={[]}
        live={false}
        onSelect={onSelect}
      />,
    )
    await userEvent.click(screen.getByText('Good morning. What brings you in today?'))
    expect(onSelect).toHaveBeenCalledWith('seg_001')
  })

  it('shows a waiting state before any speech has been transcribed', () => {
    render(
      <TranscriptPanel
        segments={[]}
        speakers={[]}
        evidence={[]}
        selectedRef={null}
        highlightedRefs={[]}
        live={false}
        onSelect={() => {}}
      />,
    )
    expect(screen.getByText('Waiting for speech')).toBeInTheDocument()
  })
})
