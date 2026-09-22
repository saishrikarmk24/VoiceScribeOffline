/**
 * Capture a Google Meet tab (or any browser tab) and send it through the
 * existing MedScribe upload/transcription pipeline.
 *
 * Chrome/Edge can include the Meet tab's audio via getDisplayMedia. The local
 * microphone is mixed in as well, because tab-share often omits the clinician
 * who is speaking into Meet from this machine. The mixed PCM is encoded as
 * 16 kHz mono WAV and uploaded with the same API the microphone recorder uses.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

import { downsample, encodeWav } from '@/hooks/useAudioRecorder'
import { api } from '@/services/api'
import { useUiStore } from '@/store/uiStore'

const TARGET_SAMPLE_RATE = 16000
const MAX_RECORDING_SECONDS = 15 * 60
const MIN_RECORDING_SECONDS = 0.4

export type MeetCaptureState = 'idle' | 'requesting' | 'recording' | 'uploading' | 'error'

export interface MeetTabCapture {
  state: MeetCaptureState
  recording: boolean
  busy: boolean
  level: number
  seconds: number
  error: string | null
  includeMicrophone: true
  micConnected: boolean
  previewStream: MediaStream | null
  start: () => Promise<void>
  stop: () => Promise<void>
  cancel: () => void
  clearError: () => void
}

type MeetDisplayOptions = DisplayMediaStreamOptions & {
  preferCurrentTab?: boolean
  selfBrowserSurface?: 'include' | 'exclude'
  surfaceSwitching?: 'include' | 'exclude'
  monitorTypeSurfaces?: 'include' | 'exclude'
}

export function describeMeetCaptureError(error: unknown): string {
  const name = (error as DOMException | undefined)?.name
  switch (name) {
    case 'NotAllowedError':
    case 'PermissionDeniedError':
    case 'AbortError':
      return 'Tab sharing was cancelled or denied. Click Share Meet tab again, pick the Google Meet tab, and tick “Share tab audio”.'
    case 'NotFoundError':
      return 'The browser could not find a shareable tab. Open Google Meet in Chrome or Edge, then try again.'
    case 'NotSupportedError':
    case 'TypeError':
      return 'This browser cannot capture tab audio. Use the latest Chrome or Edge on https or localhost.'
    case 'SecurityError':
      return 'The browser blocked display capture. Tab capture requires a secure context (https, or localhost during development).'
    default:
      return (error as Error)?.message || 'The Google Meet tab could not be captured.'
  }
}

function mixToMono(buffer: AudioBuffer): Float32Array {
  const channels = buffer.numberOfChannels
  const length = buffer.length
  const output = new Float32Array(length)
  if (channels === 1) {
    output.set(buffer.getChannelData(0))
    return output
  }
  for (let channel = 0; channel < channels; channel += 1) {
    const data = buffer.getChannelData(channel)
    for (let i = 0; i < length; i += 1) output[i] += data[i]
  }
  const scale = 1 / channels
  for (let i = 0; i < length; i += 1) output[i] *= scale
  return output
}

export function useMeetTabCapture(sessionId: string | null): MeetTabCapture {
  const [state, setState] = useState<MeetCaptureState>('idle')
  const [level, setLevel] = useState(0)
  const [seconds, setSeconds] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const includeMicrophone = true
  const [micConnected, setMicConnected] = useState(false)
  const [previewStream, setPreviewStream] = useState<MediaStream | null>(null)
  const pushToast = useUiStore((store) => store.pushToast)

  const displayStreamRef = useRef<MediaStream | null>(null)
  const micStreamRef = useRef<MediaStream | null>(null)
  const contextRef = useRef<AudioContext | null>(null)
  const processorRef = useRef<ScriptProcessorNode | null>(null)
  const sourcesRef = useRef<AudioNode[]>([])
  const chunksRef = useRef<Float32Array[]>([])
  const sampleCountRef = useRef(0)
  const captureRateRef = useRef(TARGET_SAMPLE_RATE)
  const timerRef = useRef<number | null>(null)
  const autoStopRef = useRef<(() => void) | null>(null)

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
    for (const node of sourcesRef.current) node.disconnect()
    sourcesRef.current = []
    displayStreamRef.current?.getTracks().forEach((track) => track.stop())
    displayStreamRef.current = null
    micStreamRef.current?.getTracks().forEach((track) => track.stop())
    micStreamRef.current = null
    setPreviewStream(null)
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

    if (!navigator.mediaDevices?.getDisplayMedia) {
      fail(
        'Tab capture unavailable',
        'This browser cannot share a tab. Use the latest Chrome or Edge over https or localhost.',
      )
      return
    }

    try {
      const displayOptions: MeetDisplayOptions = {
        video: {
          displaySurface: 'browser',
          frameRate: { ideal: 5, max: 15 },
        } as MediaTrackConstraints,
        audio: {
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false,
        } as MediaTrackConstraints,
        preferCurrentTab: false,
        selfBrowserSurface: 'exclude',
        surfaceSwitching: 'include',
        monitorTypeSurfaces: 'exclude',
      }

      const displayStream = await navigator.mediaDevices.getDisplayMedia(displayOptions)
      displayStreamRef.current = displayStream

      if (displayStream.getAudioTracks().length === 0) {
        displayStream.getTracks().forEach((track) => track.stop())
        fail(
          'No Meet audio',
          'The shared surface had no audio. In the Chrome picker, select the Google Meet tab (not the whole screen) and tick “Share tab audio”.',
        )
        return
      }

      displayStream.getVideoTracks().forEach((track) => {
        track.onended = () => {
          if (autoStopRef.current) autoStopRef.current()
        }
      })

      let micStream: MediaStream | null = null
      if (navigator.mediaDevices.getUserMedia) {
        try {
          micStream = await navigator.mediaDevices.getUserMedia({
            audio: {
              channelCount: 1,
              echoCancellation: true,
              noiseSuppression: true,
              autoGainControl: true,
            },
          })
          micStreamRef.current = micStream
          setMicConnected(true)
        } catch {
          setMicConnected(false)
          pushToast({
            kind: 'warning',
            title: 'Microphone not connected',
            detail: 'Your voice will NOT be recorded. Only the remote participant\'s audio from Meet will be captured. Grant microphone permission and try again.',
          })
        }
      }

      const context = new AudioContext({ sampleRate: TARGET_SAMPLE_RATE })
      contextRef.current = context
      captureRateRef.current = context.sampleRate
      if (context.state === 'suspended') await context.resume()

      const mixer = context.createGain()
      mixer.gain.value = 1
      sourcesRef.current.push(mixer)

      const tabSource = context.createMediaStreamSource(displayStream)
      sourcesRef.current.push(tabSource)
      tabSource.connect(mixer)

      if (micStream) {
        const micSource = context.createMediaStreamSource(micStream)
        const micGain = context.createGain()
        micGain.gain.value = 1.2
        sourcesRef.current.push(micSource, micGain)
        micSource.connect(micGain)
        micGain.connect(mixer)
      }

      const processor = context.createScriptProcessor(4096, 2, 1)
      processorRef.current = processor
      processor.onaudioprocess = (event) => {
        const mono = mixToMono(event.inputBuffer)
        chunksRef.current.push(mono)
        sampleCountRef.current += mono.length
        let peak = 0
        for (let i = 0; i < mono.length; i += 16) peak = Math.max(peak, Math.abs(mono[i] ?? 0))
        setLevel(peak)
        if (sampleCountRef.current / captureRateRef.current >= MAX_RECORDING_SECONDS) {
          autoStopRef.current?.()
        }
      }

      mixer.connect(processor)
      const silent = context.createGain()
      silent.gain.value = 0
      processor.connect(silent)
      silent.connect(context.destination)

      setPreviewStream(displayStream)
      const startedAt = Date.now()
      timerRef.current = window.setInterval(() => setSeconds((Date.now() - startedAt) / 1000), 250)
      setState('recording')
      pushToast({
        kind: 'success',
        title: 'Recording Google Meet',
        detail: 'Keep this window open. Press Stop when the encounter ends to transcribe it through the usual pipeline.',
      })
    } catch (err) {
      release()
      fail('Could not share Meet tab', describeMeetCaptureError(err))
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
        'The capture was too short, or no audio arrived from the Meet tab. Confirm “Share tab audio” is ticked and try again.',
      )
      return
    }

    setState('uploading')
    try {
      const file = new File([recorded.wav], `gmeet-${Date.now()}.wav`, { type: 'audio/wav' })
      const result = await api.uploadRecording(sessionId, file)
      if (!result.ok) {
        fail('No speech recognised', result.message ?? 'No speech was recognised in the Meet recording.')
        return
      }
      setState('idle')
      setSeconds(0)
      pushToast({
        kind: 'success',
        title: 'Meet recording transcribed',
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
      detail: `Capture stopped at ${MAX_RECORDING_SECONDS / 60} minutes and is being transcribed.`,
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
    includeMicrophone,
    micConnected,
    previewStream,
    start,
    stop,
    cancel,
    clearError: () => {
      setError(null)
      setState((current) => (current === 'error' ? 'idle' : current))
    },
  }
}
