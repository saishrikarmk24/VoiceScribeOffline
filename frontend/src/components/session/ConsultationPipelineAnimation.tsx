import React, { useEffect, useState } from 'react'
import {
  Activity,
  CheckCircle2,
  FileCheck2,
  Loader2,
  Mic,
  Sparkles,
  Stethoscope,
  Volume2,
} from 'lucide-react'
import { cn } from '@/utils/cn'
import type { ProcessingStage } from '@/types'

interface Props {
  stage?: ProcessingStage
  stageDetail?: string
  isUploading?: boolean
  className?: string
}

export const ConsultationPipelineAnimation: React.FC<Props> = ({
  stage = 'IDLE',
  stageDetail,
  isUploading = false,
  className,
}) => {
  const [internalStep, setInternalStep] = useState(1)

  useEffect(() => {
    if (['ASR', 'DIARIZATION', 'ROLE_ATTRIBUTION', 'TRANSCRIPT_ASSEMBLY', 'AUDIO_PREPROCESSING'].includes(stage)) {
      setInternalStep(1)
    } else if (['CLINICAL_NLP', 'EVIDENCE_LINKING'].includes(stage)) {
      setInternalStep(2)
    } else if (['LLM_STRUCTURING', 'NOTE_STATE'].includes(stage)) {
      setInternalStep(3)
    } else if (isUploading) {
      const t1 = setTimeout(() => setInternalStep(2), 2200)
      const t2 = setTimeout(() => setInternalStep(3), 4800)
      return () => {
        clearTimeout(t1)
        clearTimeout(t2)
      }
    }
  }, [stage, isUploading])

  const steps = [
    {
      step: 1,
      title: 'Speech Diarization & Transcription',
      desc: 'Transcribing medical speech and separating doctor/patient utterances',
      icon: Volume2,
      active: internalStep === 1,
      done: internalStep > 1,
    },
    {
      step: 2,
      title: 'Clinical Entity Extraction',
      desc: 'Identifying symptoms, medications, dosages, and examination findings',
      icon: Stethoscope,
      active: internalStep === 2,
      done: internalStep > 2,
    },
    {
      step: 3,
      title: 'SOAP Note Synthesis',
      desc: 'Structuring Chief Complaint, HPI, Physical Exam & Assessment Plan',
      icon: FileCheck2,
      active: internalStep === 3,
      done: false,
    },
  ]

  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center p-6 text-center select-none animate-fade-in',
        className,
      )}
    >
      <div className="relative mb-6 flex items-center justify-center">
        <div className="absolute -inset-4 rounded-full bg-teal-500/10 blur-xl animate-pulse" />
        <div className="absolute -inset-1 rounded-full border border-teal-500/20 animate-ping opacity-40" />

        <div className="relative grid h-20 w-20 place-items-center rounded-full border-2 border-teal-500/40 bg-gradient-to-tr from-teal-50 to-emerald-100 dark:from-teal-950 dark:to-slate-900 shadow-md shadow-teal-500/10">
          {internalStep === 1 && (
            <Mic className="h-9 w-9 text-teal-600 dark:text-teal-400 animate-bounce" />
          )}
          {internalStep === 2 && (
            <Activity className="h-9 w-9 text-emerald-600 dark:text-emerald-400 animate-pulse" />
          )}
          {internalStep === 3 && (
            <Sparkles className="h-9 w-9 text-amber-500 dark:text-amber-400 animate-spin" />
          )}

          <span className="absolute -top-1 right-2 h-2.5 w-2.5 rounded-full bg-teal-400 shadow-[0_0_8px_#2dd4bf] animate-ping" />
        </div>
      </div>

      <h3 className="text-base font-bold tracking-tight text-slate-900 dark:text-slate-100 flex items-center gap-2">
        <span>
          {internalStep === 1
            ? 'Transcribing Audio...'
            : internalStep === 2
              ? 'Analyzing Clinical Entities...'
              : 'Assembling Structured Note...'}
        </span>
        <Loader2 className="h-4 w-4 animate-spin text-teal-600 dark:text-teal-400 shrink-0" />
      </h3>

      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400 max-w-sm leading-relaxed">
        {stageDetail ||
          (internalStep === 1
            ? 'Translating acoustic signals into speaker-attributed dialogue turns'
            : internalStep === 2
              ? 'Extracting clinical terms, prescriptions, and ambulatory observations'
              : 'Synthesizing comprehensive SOAP clinical note with SNOMED mapping')}
      </p>

      <div className="mt-6 w-full max-w-sm rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white/70 dark:bg-slate-900/60 p-3.5 space-y-2.5 shadow-2xs">
        {steps.map((s) => (
          <div
            key={s.step}
            className={cn(
              'flex items-center gap-3 rounded-xl p-2 text-left transition-all duration-300',
              s.active
                ? 'bg-teal-50 dark:bg-teal-950/50 border border-teal-200/60 dark:border-teal-800/50'
                : s.done
                  ? 'opacity-80'
                  : 'opacity-40',
            )}
          >
            <div
              className={cn(
                'grid h-7 w-7 shrink-0 place-items-center rounded-lg text-xs font-bold transition-colors',
                s.done
                  ? 'bg-emerald-500 text-white'
                  : s.active
                    ? 'bg-teal-600 text-white shadow-xs'
                    : 'bg-slate-200 dark:bg-slate-800 text-slate-500',
              )}
            >
              {s.done ? (
                <CheckCircle2 className="h-4 w-4" />
              ) : s.active ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <span>{s.step}</span>
              )}
            </div>

            <div className="min-w-0 flex-1 leading-tight">
              <p
                className={cn(
                  'truncate text-xs font-semibold',
                  s.active
                    ? 'text-teal-900 dark:text-teal-200'
                    : s.done
                      ? 'text-slate-700 dark:text-slate-300'
                      : 'text-slate-400',
                )}
              >
                {s.title}
              </p>
              <p className="truncate text-2xs text-slate-400 dark:text-slate-500 mt-0.5">
                {s.desc}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
