import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { describeMeetCaptureError, useMeetTabCapture } from '@/hooks/useMeetTabCapture'
import { api } from '@/services/api'
import { useUiStore } from '@/store/uiStore'

const SESSION_ID = 'session-gmeet'

class FakeAudioContext {
  static lastInstance: FakeAudioContext | null = null

  sampleRate: number
  state = 'running'
  destination = {}
  processor: {
    onaudioprocess: ((event: { inputBuffer: AudioBuffer }) => void) | null
    connect: () => void
    disconnect: () => void
  } | null = null

  constructor(options?: { sampleRate?: number }) {
    this.sampleRate = options?.sampleRate ?? 48000
    FakeAudioContext.lastInstance = this
  }

  createMediaStreamSource() {
    return { connect: () => {}, disconnect: () => {} }
  }

  createScriptProcessor() {
    this.processor = { onaudioprocess: null, connect: () => {}, disconnect: () => {} }
    return this.processor
  }

  createGain() {
    return { gain: { value: 1 }, connect: () => {}, disconnect: () => {} }
  }

  async resume() {
    this.state = 'running'
  }

  async close() {
    this.state = 'closed'
  }
}

function stereoBlock(value: number, size = 4096): AudioBuffer {
  const channel = new Float32Array(size).fill(value)
  return {
    numberOfChannels: 2,
    length: size,
    getChannelData: () => channel,
  } as unknown as AudioBuffer
}

function speak(seconds: number) {
  const context = FakeAudioContext.lastInstance
  if (!context?.processor?.onaudioprocess) throw new Error('capture graph not started')
  const blockSize = 4096
  const blocks = Math.ceil((seconds * context.sampleRate) / blockSize)
  const buffer = stereoBlock(0.4, blockSize)
  for (let i = 0; i < blocks; i += 1) {
    context.processor.onaudioprocess({ inputBuffer: buffer })
  }
}

function streamWithAudio() {
  const stopped = { audio: 0, video: 0 }
  return {
    stopped,
    stream: {
      getAudioTracks: () => [{ stop: () => { stopped.audio += 1 }, onended: null }],
      getVideoTracks: () => [{ stop: () => { stopped.video += 1 }, onended: null }],
      getTracks: () => [
        { stop: () => { stopped.audio += 1 } },
        { stop: () => { stopped.video += 1 } },
      ],
    },
  }
}

let getDisplayMedia: ReturnType<typeof vi.fn>
let getUserMedia: ReturnType<typeof vi.fn>

beforeEach(() => {
  FakeAudioContext.lastInstance = null
  getDisplayMedia = vi.fn()
  getUserMedia = vi.fn()
  vi.stubGlobal('AudioContext', FakeAudioContext)
  Object.defineProperty(globalThis.navigator, 'mediaDevices', {
    configurable: true,
    value: { getDisplayMedia, getUserMedia },
  })
  useUiStore.setState({ toasts: [] })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('describeMeetCaptureError', () => {
  it('tells the user to tick Share tab audio when they cancel the picker', () => {
    expect(describeMeetCaptureError(new DOMException('x', 'NotAllowedError'))).toMatch(/Share tab audio/i)
  })
})

describe('useMeetTabCapture', () => {
  it('refuses to start when the shared surface has no audio track', async () => {
    getDisplayMedia.mockResolvedValue({
      getAudioTracks: () => [],
      getVideoTracks: () => [],
      getTracks: () => [{ stop: () => {} }],
    })

    const { result } = renderHook(() => useMeetTabCapture(SESSION_ID))
    await act(async () => {
      await result.current.start()
    })

    expect(result.current.state).toBe('error')
    expect(result.current.error).toMatch(/Share tab audio/i)
  })

  it('mixes Meet tab audio and uploads a WAV through the existing pipeline', async () => {
    const { stream } = streamWithAudio()
    getDisplayMedia.mockResolvedValue(stream)
    getUserMedia.mockResolvedValue({
      getTracks: () => [{ stop: () => {} }],
    })
    const upload = vi.spyOn(api, 'uploadRecording').mockResolvedValue({
      ok: true,
      message: 'Transcribed gmeet.wav into 4 segment(s).',
      detail: {},
    })

    const { result } = renderHook(() => useMeetTabCapture(SESSION_ID))
    await act(async () => {
      await result.current.start()
    })
    expect(result.current.recording).toBe(true)

    act(() => {
      speak(1)
    })

    await act(async () => {
      await result.current.stop()
    })

    await waitFor(() => expect(upload).toHaveBeenCalledTimes(1))
    const file = upload.mock.calls[0]?.[1] as File
    expect(file.type).toBe('audio/wav')
    expect(file.name).toMatch(/^gmeet-/)
    expect(result.current.state).toBe('idle')
  })
})
