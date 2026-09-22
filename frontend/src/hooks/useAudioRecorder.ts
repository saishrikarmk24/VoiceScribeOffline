/**
 * Browser microphone recording for a live session.
 *
 * Captures the whole take, then uploads the real recorded audio to the backend
 * when the clinician presses Stop. There is no demo or placeholder path here: if
 * permission is refused, the device fails, or the upload/transcription fails,
 * the error is reported and no transcript is produced.
 *
 * Audio is captured as 16 kHz mono PCM and encoded to WAV in the browser rather
 * than using MediaRecorder, because MediaRecorder emits WebM/Opus in Chromium
 * and WebM is not a container the transcription backend accepts. WAV is decoded
 * server-side with no ffmpeg dependency and is accepted by every supported
 * speech provider.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

import { api } from '@/services/api'
import { useUiStore } from '@/store/uiStore'

const TARGET_SAMPLE_RATE = 16000
const MAX_RECORDING_SECONDS = 15 * 60
const MIN_RECORDING_SECONDS = 0.4

export type RecorderState = 'idle' | 'requesting' | 'recording' | 'uploading' | 'error'

export interface AudioRecorder {
  state: RecorderState
  recording: boolean
  busy: boolean
  level: number
  seconds: number
  error: string | null
  start: () => Promise<void>
  stop: () => Promise<void>
  cancel: () => void
  clearError: () => void
}

export function encodeWav(samples: Float32Array, sampleRate: number): ArrayBuffer {
  const buffer = new ArrayBuffer(44 + samples.length * 2)
  const view = new DataView(buffer)
  const writeString = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i += 1) view.setUint8(offset + i, value.charCodeAt(i))
  }

  writeString(0, 'RIFF')
  view.setUint32(4, 36 + samples.length * 2, true)
  writeString(8, 'WAVE')
  writeString(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true) // PCM
  view.setUint16(22, 1, true) // mono
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * 2, true)
  view.setUint16(32, 2, true)
  view.setUint16(34, 16, true)
  writeString(36, 'data')
  view.setUint32(40, samples.length * 2, true)

  let offset = 44
  for (let i = 0; i < samples.length; i += 1) {
    const clamped = Math.max(-1, Math.min(1, samples[i]))
    view.setInt16(offset, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true)
    offset += 2
  }
  return buffer
}

export function downsample(input: Float32Array, fromRate: number, toRate: number): Float32Array {
  if (fromRate === toRate || input.length === 0) return input
  const ratio = fromRate / toRate
  const length = Math.floor(input.length / ratio)
  const output = new Float32Array(length)
  for (let i = 0; i < length; i += 1) {
    const start = Math.floor(i * ratio)
    const end = Math.min(Math.floor((i + 1) * ratio), input.length)
    let sum = 0
    for (let j = start; j < end; j += 1) sum += input[j]
    output[i] = end > start ? sum / (end - start) : 0
  }
  return output
}

/** Turns getUserMedia failures into something a clinician can act on. */
export function describeMicrophoneError(error: unknown): string {
  const name = (error as DOMException | undefined)?.name
  switch (name) {
    case 'NotAllowedError':
    case 'PermissionDeniedError':
      return 'Microphone permission was denied. Allow microphone access for this site in your browser settings, then try again.'
    case 'SecurityError':
      return 'The browser blocked microphone access. Microphone capture requires a secure context (https, or localhost during development).'
    case 'NotFoundError':
    case 'DevicesNotFoundError':
      return 'No microphone was found. Connect a microphone and try again.'
    case 'NotReadableError':
    case 'TrackStartError':
      return 'The microphone is in use by another application, or the operating system blocked access to it.'
    case 'OverconstrainedError':
      return 'The selected microphone cannot record mono audio. Try a different input device.'
    case 'AbortError':
      return 'Microphone access was interrupted. Try again.'
    default:
      return (error as Error)?.message || 'The microphone could not be started.'
  }
}

export function useAudioRecorder(sessionId: string | null): AudioRecorder {
  const [state, setState] = useState<RecorderState>('idle')
  const [level, setLevel] = useState(0)
  const [seconds, setSeconds] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const pushToast = useUiStore((store) => store.pushToast)

  const streamRef = useRef<MediaStream | null>(null)
  const contextRef = useRef<AudioContext | null>(null)
  const processorRef = useRef<ScriptProcessorNode | null>(null)
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null)
  const chunksRef = useRef<Float32Array[]>([])
  const sampleCountRef = useRef(0)
  const captureRateRef = useRef(TARGET_SAMPLE_RATE)
  const timerRef = useRef<number | null>(null)
  const autoStopRef = useRef<(() => void) | null>(null)

  /** Releases the microphone and tears down the audio graph. */
  const release = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current)
      timerRef.current = null
    }
    if (processorRef.current) {
      processorRef.current.onaudioprocess = null
      processorRef.current.disconnect()
      processorRef.current = null
    }
    sourceRef.current?.disconnect()
    sourceRef.current = null
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
    const context = contextRef.current
    contextRef.current = null
    if (context && context.state !== 'closed') void context.close()
    setLevel(0)
  }, [])

  const takeRecordedAudio = useCallback((): { wav: ArrayBuffer; duration: number } | null => {
    const chunks = chunksRef.current
    chunksRef.current = []
    const total = sampleCountRef.current
    sampleCountRef.current = 0
    if (!total) return null

    const merged = new Float32Array(total)
    let offset = 0
    for (const chunk of chunks) {
      merged.set(chunk, offset)
      offset += chunk.length
    }
    const resampled = downsample(merged, captureRateRef.current, TARGET_SAMPLE_RATE)
    return {
      wav: encodeWav(resampled, TARGET_SAMPLE_RATE),
      duration: resampled.length / TARGET_SAMPLE_RATE,
    }
  }, [])

  const fail = useCallback(
    (title: string, message: string) => {
      setError(message)
      setState('error')
      pushToast({ kind: 'error', title, detail: message })
    },
    [pushToast],
  )

  const start = useCallback(async () => {
    if (!sessionId || state === 'recording' || state === 'requesting' || state === 'uploading') return
    setError(null)
    setSeconds(0)
    chunksRef.current = []
    sampleCountRef.current = 0
    setState('requesting')

    if (!navigator.mediaDevices?.getUserMedia) {
      fail(
        'Microphone unavailable',
        'This browser does not expose microphone capture. Use a current version of Chrome, Edge, Firefox or Safari over https or localhost.',
      )
      return
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      })
      streamRef.current = stream

      const context = new AudioContext({ sampleRate: TARGET_SAMPLE_RATE })
      contextRef.current = context
      // The browser may refuse the requested rate; record whatever it gives us
      // and resample on the way out.
      captureRateRef.current = context.sampleRate
      if (context.state === 'suspended') await context.resume()

      const source = context.createMediaStreamSource(stream)
      sourceRef.current = source
      const processor = context.createScriptProcessor(4096, 1, 1)
      processorRef.current = processor

      processor.onaudioprocess = (event) => {
        const input = event.inputBuffer.getChannelData(0)
        chunksRef.current.push(new Float32Array(input))
        sampleCountRef.current += input.length

        let peak = 0
        for (let i = 0; i < input.length; i += 16) peak = Math.max(peak, Math.abs(input[i]))
        setLevel(peak)

        if (sampleCountRef.current / captureRateRef.current >= MAX_RECORDING_SECONDS) {
          autoStopRef.current?.()
        }
      }

      source.connect(processor)
      // ScriptProcessor only fires while connected to a destination; a zero-gain
      // node keeps the graph alive without echoing the microphone to the speakers.
      const silent = context.createGain()
      silent.gain.value = 0
      processor.connect(silent)
      silent.connect(context.destination)

      const startedAt = Date.now()
      timerRef.current = window.setInterval(() => setSeconds((Date.now() - startedAt) / 1000), 250)

      setState('recording')
      pushToast({
        kind: 'success',
        title: 'Recording',
        detail: 'Speak normally. Press Stop when the encounter is finished to transcribe it.',
      })
    } catch (err) {
      release()
      fail('Microphone unavailable', describeMicrophoneError(err))
    }
  }, [fail, pushToast, release, sessionId, state])

  const stop = useCallback(async () => {
    if (!sessionId || state !== 'recording') return
    const elapsed = sampleCountRef.current / captureRateRef.current
    release()

    const recorded = takeRecordedAudio()
    if (!recorded || elapsed < MIN_RECORDING_SECONDS) {
      fail(
        'Nothing recorded',
        'The recording was too short to transcribe. Hold Record for at least a second while speaking.',
      )
      return
    }

    setState('uploading')
    try {
      const file = new File([recorded.wav], `recording-${Date.now()}.wav`, { type: 'audio/wav' })
      const result = await api.uploadRecording(sessionId, file)
      if (!result.ok) {
        // The backend recognised no speech. Reported as-is; never backfilled.
        fail('No speech recognised', result.message ?? 'No speech was recognised in the recording.')
        return
      }
      setState('idle')
      setSeconds(0)
      pushToast({
        kind: 'success',
        title: 'Recording transcribed',
        detail: result.message ?? 'The transcript and clinical note have been updated.',
      })
    } catch (err) {
      fail('Transcription failed', (err as Error).message)
    }
  }, [fail, pushToast, release, sessionId, state, takeRecordedAudio])

  const cancel = useCallback(() => {
    release()
    chunksRef.current = []
    sampleCountRef.current = 0
    setSeconds(0)
    setState('idle')
  }, [release])

  autoStopRef.current = () => {
    void stop()
    pushToast({
      kind: 'warning',
      title: 'Recording limit reached',
      detail: `Recording stopped at ${MAX_RECORDING_SECONDS / 60} minutes and is being transcribed.`,
    })
  }

  useEffect(() => release, [release])

  return {
    state,
    recording: state === 'recording',
    busy: state === 'requesting' || state === 'uploading',
    level,
    seconds,
    error,
    start,
    stop,
    cancel,
    clearError: () => {
      setError(null)
      setState((current) => (current === 'error' ? 'idle' : current))
    },
  }
}
