import { useEffect, useRef, useState } from 'react'
import { Activity, Check, Mic, RotateCcw, Square, X } from 'lucide-react'

import { Spinner } from '@/components/ui/primitives'
import { downsample, encodeWav } from '@/hooks/useAudioRecorder'
import { api } from '@/services/api'

interface Props {
  open: boolean
  onClose: () => void
  onAddVitals: (vitalsSummary: string, medsSummary: string) => Promise<void>
}

const TARGET_SAMPLE_RATE = 16000

export function VitalsDictationModal({ open, onClose, onAddVitals }: Props) {
  const [dictatedText, setDictatedText] = useState('')
  const [bp, setBp] = useState('')
  const [sugar, setSugar] = useState('')
  const [pulse, setPulse] = useState('')
  const [spo2, setSpo2] = useState('')
  const [temp, setTemp] = useState('')
  const [meds, setMeds] = useState('')
  const [isRecording, setIsRecording] = useState(false)
  const [transcribing, setTranscribing] = useState(false)
  const [audioLevel, setAudioLevel] = useState(0)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [showManual, setShowManual] = useState(false)

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const recognitionRef = useRef<any>(null)
  const isListeningRef = useRef(false)
  const finalTranscriptRef = useRef('')

  const audioContextRef = useRef<AudioContext | null>(null)
  const mediaStreamRef = useRef<MediaStream | null>(null)
  const processorRef = useRef<ScriptProcessorNode | null>(null)
  const audioChunksRef = useRef<Float32Array[]>([])

  const cleanupAudio = () => {
    isListeningRef.current = false
    setIsRecording(false)
    setAudioLevel(0)

    if (recognitionRef.current) {
      try {
        recognitionRef.current.abort()
      } catch {}
      recognitionRef.current = null
    }

    if (processorRef.current) {
      try {
        processorRef.current.disconnect()
      } catch {}
      processorRef.current = null
    }

    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop())
      mediaStreamRef.current = null
    }

    if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
      try {
        void audioContextRef.current.close()
      } catch {}
      audioContextRef.current = null
    }
  }

  useEffect(() => {
    if (!open) {
      cleanupAudio()
      setErrorMsg(null)
    }
    return () => cleanupAudio()
  }, [open])

  if (!open) return null

  const startListening = async () => {
    setErrorMsg(null)
    audioChunksRef.current = []

    let stream: MediaStream
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      })
      mediaStreamRef.current = stream
    } catch {
      setErrorMsg('Microphone access was denied. Please allow microphone permissions in your browser.')
      return
    }

    // Setup AudioContext for live PCM capture and audio level metering
    try {
      const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
      const ctx = new AudioCtx()
      audioContextRef.current = ctx
      const source = ctx.createMediaStreamSource(stream)
      const processor = ctx.createScriptProcessor(4096, 1, 1)
      processorRef.current = processor

      processor.onaudioprocess = (e) => {
        const input = e.inputBuffer.getChannelData(0)
        audioChunksRef.current.push(new Float32Array(input))

        let sum = 0
        for (let i = 0; i < input.length; i++) {
          sum += input[i] * input[i]
        }
        const rms = Math.sqrt(sum / input.length)
        setAudioLevel(Math.min(1, rms * 5))
      }

      source.connect(processor)
      processor.connect(ctx.destination)
    } catch (err) {
      console.warn('AudioContext recording initialization issue:', err)
    }

    // Start Web Speech API in parallel for instant display
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const win = window as any
    const SpeechRecognition = win.SpeechRecognition || win.webkitSpeechRecognition

    if (SpeechRecognition) {
      try {
        const recognition = new SpeechRecognition()
        recognition.continuous = true
        recognition.interimResults = true
        recognition.maxAlternatives = 1
        recognition.lang = 'en-US'

        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        recognition.onresult = (event: any) => {
          let interim = ''
          for (let i = event.resultIndex; i < event.results.length; i++) {
            const transcript = event.results[i][0].transcript
            if (event.results[i].isFinal) {
              finalTranscriptRef.current += (finalTranscriptRef.current ? ' ' : '') + transcript.trim()
            } else {
              interim += transcript
            }
          }
          const fullText = finalTranscriptRef.current + (interim ? ' ' + interim.trim() : '')
          if (fullText.trim()) {
            setDictatedText(fullText.trim())
          }
        }

        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        recognition.onerror = (event: any) => {
          if (event.error === 'no-speech' || event.error === 'audio-capture') return
        }

        recognition.onend = () => {
          if (isListeningRef.current) {
            try {
              recognition.start()
            } catch {}
          }
        }

        recognitionRef.current = recognition
        recognition.start()
      } catch (err) {
        console.warn('SpeechRecognition initialization issue:', err)
      }
    }

    isListeningRef.current = true
    setIsRecording(true)
  }

  const stopListening = async () => {
    isListeningRef.current = false
    setIsRecording(false)
    setAudioLevel(0)

    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop()
      } catch {}
    }

    const currentText = dictatedText.trim()
    const chunks = audioChunksRef.current

    // If Web Speech API already transcribed text, we're done
    if (currentText.length > 0) {
      cleanupAudio()
      return
    }

    // If no text was captured by Web Speech API, fallback to backend WAV transcription
    if (chunks.length > 0 && audioContextRef.current) {
      setTranscribing(true)
      try {
        const sampleRate = audioContextRef.current.sampleRate
        const totalSamples = chunks.reduce((acc, c) => acc + c.length, 0)
        const merged = new Float32Array(totalSamples)
        let offset = 0
        for (const chunk of chunks) {
          merged.set(chunk, offset)
          offset += chunk.length
        }
        const downsampled = downsample(merged, sampleRate, TARGET_SAMPLE_RATE)
        const wavBuffer = encodeWav(downsampled, TARGET_SAMPLE_RATE)
        const wavBlob = new Blob([wavBuffer], { type: 'audio/wav' })

        const res = await api.transcribeClip(wavBlob)
        if (res.detail?.text) {
          const text = res.detail.text.trim()
          setDictatedText((prev) => (prev ? `${prev} ${text}` : text))
          finalTranscriptRef.current = text
        } else if (res.message && !res.ok) {
          setErrorMsg(res.message)
        }
      } catch (err) {
        console.warn('Backend clip transcription failed:', err)
      } finally {
        setTranscribing(false)
      }
    }

    cleanupAudio()
  }

  const handleClear = () => {
    finalTranscriptRef.current = ''
    setDictatedText('')
  }

  const handleApply = async () => {
    if (isRecording) {
      await stopListening()
    }
    setSaving(true)
    try {
      const vitalsParts: string[] = []
      if (bp.trim()) vitalsParts.push(`BP: ${bp.trim()} mmHg`)
      if (sugar.trim()) vitalsParts.push(`Blood Sugar: ${sugar.trim()} mg/dL`)
      if (pulse.trim()) vitalsParts.push(`Pulse: ${pulse.trim()} bpm`)
      if (spo2.trim()) vitalsParts.push(`SpO2: ${spo2.trim()}%`)
      if (temp.trim()) vitalsParts.push(`Temp: ${temp.trim()} °F`)
      if (dictatedText.trim()) vitalsParts.push(dictatedText.trim())

      const vitalsText = vitalsParts.join(', ')
      await onAddVitals(vitalsText, meds.trim())
      onClose()
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 p-4 backdrop-blur-[2px]"
      role="dialog"
      aria-modal="true"
    >
      <div className="w-full max-w-lg rounded-3xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-raised max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3">
          <div>
            <h3 className="text-base font-bold text-slate-900 dark:text-slate-100">Clinical Dictation & Vitals Entry</h3>
            <p className="text-2xs text-slate-500 dark:text-slate-400">Record or enter patient vitals, physical observations, and medications.</p>
          </div>
          <button
            type="button"
            onClick={() => {
              cleanupAudio()
              onClose()
            }}
            className="rounded-full p-1 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-600 dark:hover:text-slate-300 transition"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="space-y-4 pt-4">
          {errorMsg ? (
            <div className="rounded-xl border border-rose-200 dark:border-rose-900/60 bg-rose-50 dark:bg-rose-950/50 p-3 text-xs text-rose-800 dark:text-rose-300">
              {errorMsg}
            </div>
          ) : null}

          <div className="rounded-2xl border border-slate-200/90 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950/60 p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div
                  className={`grid h-8 w-8 place-items-center rounded-xl transition ${
                    isRecording ? 'bg-rose-600 text-white animate-pulse' : 'bg-teal-700 text-white'
                  }`}
                >
                  <Mic className="h-4 w-4" aria-hidden />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h4 className="text-xs font-bold text-slate-800 dark:text-slate-200">Voice Dictation</h4>
                    {isRecording ? (
                      <span className="inline-flex items-center gap-1.5 rounded-full bg-rose-100 dark:bg-rose-950/60 px-2 py-0.5 text-2xs font-semibold text-rose-800 dark:text-rose-300">
                        <span className="h-1.5 w-1.5 rounded-full bg-rose-600 animate-ping" />
                        Listening Active
                      </span>
                    ) : transcribing ? (
                      <span className="inline-flex items-center gap-1.5 rounded-full bg-teal-100 dark:bg-teal-950/60 px-2 py-0.5 text-2xs font-semibold text-teal-800 dark:text-teal-300">
                        <Spinner className="h-3 w-3 text-teal-700 dark:text-teal-400" /> Transcribing Audio…
                      </span>
                    ) : null}
                  </div>
                  <p className="text-2xs text-slate-500 dark:text-slate-400">
                    Dictate clinical observations (e.g. &ldquo;BP 120/80, pulse 72, blood sugar 110, on Metformin 500mg&rdquo;)
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-1.5">
                {dictatedText ? (
                  <button
                    type="button"
                    onClick={handleClear}
                    title="Clear transcript"
                    className="btn-secondary !py-1 text-xs text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
                  >
                    <RotateCcw className="h-3.5 w-3.5" />
                  </button>
                ) : null}

                <button
                  type="button"
                  onClick={isRecording ? () => void stopListening() : () => void startListening()}
                  disabled={transcribing}
                  className={
                    isRecording
                      ? 'btn-danger !py-1.5 text-xs font-semibold shadow-sm'
                      : 'btn-teal !py-1.5 text-xs font-semibold shadow-sm'
                  }
                >
                  {isRecording ? (
                    <>
                      <Square className="h-3.5 w-3.5 fill-current" aria-hidden /> Stop Dictation
                    </>
                  ) : (
                    <>
                      <Mic className="h-3.5 w-3.5" aria-hidden /> Start Speaking
                    </>
                  )}
                </button>
              </div>
            </div>

            {/* Live Audio Level Meter */}
            {isRecording ? (
              <div className="mt-3 flex items-center gap-2">
                <span className="text-2xs text-slate-500 dark:text-slate-400">Voice Input:</span>
                <div className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
                  <div
                    className="absolute inset-y-0 left-0 rounded-full bg-teal-600 dark:bg-teal-400 transition-[width] duration-75"
                    style={{ width: `${Math.min(100, Math.round(audioLevel * 100))}%` }}
                  />
                </div>
              </div>
            ) : null}

            <textarea
              value={dictatedText}
              onChange={(e) => {
                setDictatedText(e.target.value)
                finalTranscriptRef.current = e.target.value
              }}
              placeholder="Spoken or typed vitals dictation... (e.g. Blood pressure is 120/80, pulse 72 bpm, random blood glucose 105 mg/dL, patient is on Aspirin 75mg once daily)"
              rows={3}
              className="field-input mt-3 text-xs dark:bg-slate-950 dark:border-slate-700 dark:text-slate-100"
            />
          </div>

          <div>
            <button
              type="button"
              onClick={() => setShowManual(!showManual)}
              className="flex items-center gap-1.5 text-xs font-semibold text-slate-600 dark:text-slate-300 hover:text-teal-700 dark:hover:text-teal-400 transition"
            >
              <Activity className="h-3.5 w-3.5 text-slate-400" aria-hidden />
              <span>{showManual ? 'Hide Quick Fields' : 'Optional Structured Entry Fields'}</span>
            </button>

            {showManual ? (
              <div className="mt-3 grid grid-cols-2 sm:grid-cols-3 gap-2.5 rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/60 p-3.5">
                <label className="text-2xs font-semibold text-slate-600 dark:text-slate-400">
                  Blood Pressure (BP)
                  <input
                    type="text"
                    placeholder="e.g. 120/80"
                    value={bp}
                    onChange={(e) => setBp(e.target.value)}
                    className="field-input mt-1 text-xs dark:bg-slate-950 dark:border-slate-700 dark:text-slate-100"
                  />
                </label>

                <label className="text-2xs font-semibold text-slate-600 dark:text-slate-400">
                  Blood Sugar / Glucose
                  <input
                    type="text"
                    placeholder="e.g. 110 mg/dL"
                    value={sugar}
                    onChange={(e) => setSugar(e.target.value)}
                    className="field-input mt-1 text-xs dark:bg-slate-950 dark:border-slate-700 dark:text-slate-100"
                  />
                </label>

                <label className="text-2xs font-semibold text-slate-600 dark:text-slate-400">
                  Pulse / Heart Rate
                  <input
                    type="text"
                    placeholder="e.g. 74 bpm"
                    value={pulse}
                    onChange={(e) => setPulse(e.target.value)}
                    className="field-input mt-1 text-xs dark:bg-slate-950 dark:border-slate-700 dark:text-slate-100"
                  />
                </label>

                <label className="text-2xs font-semibold text-slate-600 dark:text-slate-400">
                  SpO2 (%)
                  <input
                    type="text"
                    placeholder="e.g. 98%"
                    value={spo2}
                    onChange={(e) => setSpo2(e.target.value)}
                    className="field-input mt-1 text-xs dark:bg-slate-950 dark:border-slate-700 dark:text-slate-100"
                  />
                </label>

                <label className="text-2xs font-semibold text-slate-600 dark:text-slate-400">
                  Temperature (°F)
                  <input
                    type="text"
                    placeholder="e.g. 98.6"
                    value={temp}
                    onChange={(e) => setTemp(e.target.value)}
                    className="field-input mt-1 text-xs dark:bg-slate-950 dark:border-slate-700 dark:text-slate-100"
                  />
                </label>

                <label className="text-2xs font-semibold text-slate-600 dark:text-slate-400 sm:col-span-3">
                  Current Medications & Supplements
                  <input
                    type="text"
                    placeholder="e.g. Metformin 500mg, Atorvastatin 10mg, Omega-3"
                    value={meds}
                    onChange={(e) => setMeds(e.target.value)}
                    className="field-input mt-1 text-xs dark:bg-slate-950 dark:border-slate-700 dark:text-slate-100"
                  />
                </label>
              </div>
            ) : null}
          </div>

          <div className="flex items-center justify-end gap-2 border-t border-slate-100 dark:border-slate-800 pt-3">
            <button
              type="button"
              onClick={() => {
                cleanupAudio()
                onClose()
              }}
              className="btn-secondary text-xs"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => void handleApply()}
              disabled={saving || (!dictatedText.trim() && !bp.trim() && !sugar.trim() && !pulse.trim() && !meds.trim())}
              className="btn-primary text-xs"
            >
              {saving ? <Spinner className="text-white" /> : <Check className="h-3.5 w-3.5" aria-hidden />}
              Apply to Consultation Note
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

