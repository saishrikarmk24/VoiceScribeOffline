import { beforeEach, describe, expect, it } from 'vitest'

import { selectEvidenceByTarget, useSessionStore } from '@/store/sessionStore'
import type { SocketEvent } from '@/types'

import { entities, evidence, note, segments, speakers } from './fixtures'

function event<T>(type: SocketEvent['type'], payload: T, sequence = 1): SocketEvent {
  return { type, session_id: 'session-1', payload: payload as never, emitted_at: new Date().toISOString(), sequence }
}

describe('session store', () => {
  beforeEach(() => {
    useSessionStore.setState({
      segments: [],
      speakers: [],
      entities: [],
      note: null,
      evidence: [],
      errors: [],
      lastNoteChange: null,
      stage: 'IDLE',
      completed: false,
    })
  })

  it('appends transcript segments in sequence order without duplicating refs', () => {
    const { applyEvent } = useSessionStore.getState()
    applyEvent(event('TRANSCRIPT_UPDATE', { segments: [segments[1]] }))
    applyEvent(event('TRANSCRIPT_UPDATE', { segments: [segments[0]] }, 2))
    applyEvent(event('TRANSCRIPT_UPDATE', { segments: [segments[1]] }, 3))

    const stored = useSessionStore.getState().segments
    expect(stored.map((segment) => segment.ref)).toEqual(['seg_001', 'seg_002'])
  })

  it('records which note sections the last AI pass changed', () => {
    const { applyEvent } = useSessionStore.getState()
    applyEvent(
      event('NOTE_UPDATE', {
        note,
        changed_sections: ['chief_complaint'],
        change_summary: 'Updated chief complaint',
      }),
    )

    const state = useSessionStore.getState()
    expect(state.note?.version).toBe(2)
    expect(state.lastNoteChange?.sections).toEqual(['chief_complaint'])
  })

  it('keeps the session usable when the AI layer reports an error', () => {
    const { applyEvent } = useSessionStore.getState()
    applyEvent(event('TRANSCRIPT_UPDATE', { segments }))
    applyEvent(
      event(
        'PROCESSING_ERROR',
        { code: 'LLM_TIMEOUT', message: 'Gemini timed out', stage: 'LLM_STRUCTURING', recoverable: true },
        2,
      ),
    )

    const state = useSessionStore.getState()
    expect(state.segments).toHaveLength(3)
    expect(state.errors[0].code).toBe('LLM_TIMEOUT')
    expect(state.errors[0].recoverable).toBe(true)
  })

  it('deduplicates repeated errors of the same code', () => {
    const { applyEvent } = useSessionStore.getState()
    const payload = { code: 'LLM_RATE_LIMIT', message: 'slow down', stage: 'LLM_STRUCTURING', recoverable: true }
    applyEvent(event('PROCESSING_ERROR', payload))
    applyEvent(event('PROCESSING_ERROR', payload, 2))
    expect(useSessionStore.getState().errors).toHaveLength(1)
  })

  it('replaces local state from a reconnect snapshot', () => {
    const { applyEvent } = useSessionStore.getState()
    applyEvent(
      event('STATE_SNAPSHOT', {
        segments,
        speakers,
        entities,
        note,
        evidence,
        stage: 'CLINICAL_NLP',
      }),
    )

    const state = useSessionStore.getState()
    expect(state.segments).toHaveLength(3)
    expect(state.speakers).toHaveLength(2)
    expect(state.entities).toHaveLength(2)
    expect(state.stage).toBe('CLINICAL_NLP')
  })

  it('groups evidence links by the statement they support', () => {
    expect(selectEvidenceByTarget(evidence)).toEqual({ chief_complaint: [evidence[0]] })
  })
})
