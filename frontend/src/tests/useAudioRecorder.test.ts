/**
 * The Record button must capture real microphone audio and upload it, and must
 * fail visibly rather than substituting demo content.
 */

import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  describeMicrophoneError,
  downsample,
  encodeWav,
  useAudioRecorder,
} from '@/hooks/useAudioRecorder'
import { api } from '@/services/api'
import { useUiStore } from '@/store/uiStore'

const SESSION_ID = 'session-1'

/** Minimal AudioContext/MediaStream test doubles; jsdom provides neither. */
class FakeAudioContext {
  static lastInstance: FakeAudioContext | null = null

  sampleRate: number
  state = 'running'
  destination = {}
  closed = false
  processor: {
    onaudioprocess: ((event: { inputBuffer: { getChannelData: () => Float32Array } }) => void) | null
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
    return { gain: { value: 1 }, connect: () => {} }
  }

  async resume() {
    this.state = 'running'
  }

  async close() {
    this.closed = true
    this.state = 'closed'
  }
}

function stopTracker() {
  const stopped = { count: 0 }
  const stream = {
    getTracks: () => [
      {
        stop: () => {
          stopped.count += 1
        },
      },
    ],
  }
  return { stopped, stream }
}

/** Feeds `seconds` of loud audio through the capture graph. */
function speak(seconds: number) {
  const context = FakeAudioContext.lastInstance
  if (!context?.processor?.onaudioprocess) throw new Error('capture graph not started')
  const blockSize = 4096
  const blocks = Math.ceil((seconds * context.sampleRate) / blockSize)
  const block = new Float32Array(blockSize).fill(0.5)
  for (let i = 0; i < blocks; i += 1) {
    context.processor.onaudioprocess({ inputBuffer: { getChannelData: () => block } })
  }
}

let getUserMedia: ReturnType<typeof vi.fn>

beforeEach(() => {
  FakeAudioContext.lastInstance = null
  getUserMedia = vi.fn()
  vi.stubGlobal('AudioContext', FakeAudioContext)
  Object.defineProperty(globalThis.navigator, 'mediaDevices', {
    configurable: true,
    value: { getUserMedia },
  })
  useUiStore.setState({ toasts: [] })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('WAV encoding', () => {
  it('writes a 16-bit mono PCM header the backend can decode', () => {
    const buffer = encodeWav(new Float32Array([0, 0.5, -0.5]), 16000)
    const view = new DataView(buffer)
    const tag = (offset: number) =>
      String.fromCharCode(view.getUint8(offset), view.getUint8(offset + 1), view.getUint8(offset + 2), view.getUint8(offset + 3))

    expect(tag(0)).toBe('RIFF')
    expect(tag(8)).toBe('WAVE')
    expect(view.getUint16(20, true)).toBe(1) // PCM
    expect(view.getUint16(22, true)).toBe(1) // mono
    expect(view.getUint32(24, true)).toBe(16000)
    expect(view.getUint16(34, true)).toBe(16)
    expect(buffer.byteLength).toBe(44 + 3 * 2)
  })

  it('resamples the browser capture rate down to 16 kHz', () => {
    const input = new Float32Array(48000).fill(0.25)
    const output = downsample(input, 48000, 16000)
    expect(output.length).toBe(16000)
    expect(output[0]).toBeCloseTo(0.25, 5)
  })
})

describe('microphone errors', () => {
  it('explains a denied permission instead of failing silently', () => {
    const denied = new DOMException('Permission denied', 'NotAllowedError')
    expect(describeMicrophoneError(denied)).toMatch(/permission was denied/i)
  })

  it('explains a missing device and an insecure context', () => {
    expect(describeMicrophoneError(new DOMException('x', 'NotFoundError'))).toMatch(/No microphone/i)
    expect(describeMicrophoneError(new DOMException('x', 'SecurityError'))).toMatch(/secure context/i)
  })
})

describe('useAudioRecorder', () => {
  it('records the microphone and uploads the captured audio as WAV', async () => {
    const { stream, stopped } = stopTracker()
    getUserMedia.mockResolvedValue(stream)
    const upload = vi
      .spyOn(api, 'uploadRecording')
      .mockResolvedValue({ ok: true, message: 'Transcribed take.wav into 2 segment(s).', detail: {} })

    const { result } = renderHook(() => useAudioRecorder(SESSION_ID))

    await act(async () => {
      await result.current.start()
    })
    expect(getUserMedia).toHaveBeenCalledWith(
      expect.objectContaining({ audio: expect.objectContaining({ channelCount: 1 }) }),
    )
    expect(result.current.recording).toBe(true)

    await act(async () => {
      speak(2)
    })

    await act(async () => {
      await result.current.stop()
    })

    expect(upload).toHaveBeenCalledTimes(1)
    const [sessionId, file] = upload.mock.calls[0]
    expect(sessionId).toBe(SESSION_ID)
    expect(file.type).toBe('audio/wav')
    expect(file.name).toMatch(/\.wav$/)
    // Two seconds of 16 kHz mono PCM16 plus the 44-byte header.
    expect(file.size).toBeGreaterThan(2 * 16000 * 2 * 0.9)

    await waitFor(() => expect(result.current.state).toBe('idle'))
    expect(result.current.error).toBeNull()
    // The microphone is released once the take is finished.
    expect(stopped.count).toBe(1)
    expect(FakeAudioContext.lastInstance?.closed).toBe(true)
  })

  it('reports denied permission and uploads nothing', async () => {
    getUserMedia.mockRejectedValue(new DOMException('Permission denied', 'NotAllowedError'))
    const upload = vi.spyOn(api, 'uploadRecording')

    const { result } = renderHook(() => useAudioRecorder(SESSION_ID))
    await act(async () => {
      await result.current.start()
    })

    expect(result.current.state).toBe('error')
    expect(result.current.error).toMatch(/permission was denied/i)
    expect(result.current.recording).toBe(false)
    expect(upload).not.toHaveBeenCalled()
    expect(useUiStore.getState().toasts.some((toast) => toast.kind === 'error')).toBe(true)
  })

  it('surfaces an upload failure without falling back to demo content', async () => {
    const { stream } = stopTracker()
    getUserMedia.mockResolvedValue(stream)
    vi.spyOn(api, 'uploadRecording').mockRejectedValue(
      new Error('ASR_PROVIDER=gemini requires GEMINI_API_KEY.'),
    )

    const { result } = renderHook(() => useAudioRecorder(SESSION_ID))
    await act(async () => {
      await result.current.start()
    })
    await act(async () => {
      speak(1.5)
    })
    await act(async () => {
      await result.current.stop()
    })

    expect(result.current.state).toBe('error')
    expect(result.current.error).toMatch(/GEMINI_API_KEY/)
  })

  it('reports a recording the backend could not transcribe', async () => {
    const { stream } = stopTracker()
    getUserMedia.mockResolvedValue(stream)
    vi.spyOn(api, 'uploadRecording').mockResolvedValue({
      ok: false,
      message: 'No speech was recognised in this recording.',
      detail: {},
    })

    const { result } = renderHook(() => useAudioRecorder(SESSION_ID))
    await act(async () => {
      await result.current.start()
    })
    await act(async () => {
      speak(1.5)
    })
    await act(async () => {
      await result.current.stop()
    })

    expect(result.current.state).toBe('error')
    expect(result.current.error).toMatch(/No speech was recognised/i)
  })

  it('refuses to upload a take with no captured audio', async () => {
    const { stream } = stopTracker()
    getUserMedia.mockResolvedValue(stream)
    const upload = vi.spyOn(api, 'uploadRecording')

    const { result } = renderHook(() => useAudioRecorder(SESSION_ID))
    await act(async () => {
      await result.current.start()
    })
    await act(async () => {
      await result.current.stop()
    })

    expect(upload).not.toHaveBeenCalled()
    expect(result.current.error).toMatch(/too short/i)
  })

  it('discards a take and releases the microphone on cancel', async () => {
    const { stream, stopped } = stopTracker()
    getUserMedia.mockResolvedValue(stream)
    const upload = vi.spyOn(api, 'uploadRecording')

    const { result } = renderHook(() => useAudioRecorder(SESSION_ID))
    await act(async () => {
      await result.current.start()
    })
    await act(async () => {
      speak(1)
    })
    act(() => {
      result.current.cancel()
    })

    expect(result.current.state).toBe('idle')
    expect(stopped.count).toBe(1)
    expect(upload).not.toHaveBeenCalled()
  })

  it('does nothing without a session', async () => {
    const { result } = renderHook(() => useAudioRecorder(null))
    await act(async () => {
      await result.current.start()
    })
    expect(getUserMedia).not.toHaveBeenCalled()
    expect(result.current.state).toBe('idle')
  })
})
