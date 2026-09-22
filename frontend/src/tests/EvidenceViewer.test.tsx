import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { EvidenceViewer } from '@/components/session/EvidenceViewer'
import { api } from '@/services/api'

import { evidence, segments } from './fixtures'

describe('EvidenceViewer', () => {
  it('renders the full provenance chain for a clinical statement', async () => {
    vi.spyOn(api, 'evidenceDetail').mockResolvedValue({
      target_key: 'chief_complaint',
      clinical_statement: 'Chest discomfort since yesterday evening.',
      chain: [{ evidence: evidence[0], segment: segments[1], audio_chunk_id: 'a1b2c3d4-0000' }],
      validated_count: 1,
      total_count: 1,
    })

    render(
      <EvidenceViewer
        sessionId="session-1"
        targetKey="chief_complaint"
        statement="Chest discomfort since yesterday evening."
        onClose={() => {}}
        onHighlight={() => {}}
      />,
    )

    expect(await screen.findByText("I've been having chest discomfort since yesterday evening.")).toBeInTheDocument()
    expect(screen.getByText('Patient')).toBeInTheDocument()
    expect(screen.getByText('00:00:03')).toBeInTheDocument()
    expect(screen.getByText('seg_002')).toBeInTheDocument()
    expect(screen.getByText('1/1 validated')).toBeInTheDocument()
  })

  it('flags a statement that cannot be traced to the transcript', async () => {
    vi.spyOn(api, 'evidenceDetail').mockResolvedValue({
      target_key: 'assessment',
      clinical_statement: 'Not mentioned',
      chain: [],
      validated_count: 0,
      total_count: 0,
    })

    render(
      <EvidenceViewer
        sessionId="session-1"
        targetKey="assessment"
        statement="Not mentioned"
        onClose={() => {}}
        onHighlight={() => {}}
      />,
    )

    expect(await screen.findByText('No transcript evidence')).toBeInTheDocument()
    expect(screen.getByText('REVIEW REQUIRED')).toBeInTheDocument()
  })
})
