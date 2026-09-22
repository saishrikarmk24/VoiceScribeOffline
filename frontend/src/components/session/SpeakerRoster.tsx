import { useState } from 'react'
import { UserCog } from 'lucide-react'

import { EmptyState, Panel, StatusDot } from '@/components/ui/primitives'
import { ROLE_STYLES, SPEAKER_ROLES } from '@/constants'
import { api } from '@/services/api'
import { useUiStore } from '@/store/uiStore'
import type { Speaker, SpeakerRole } from '@/types'
import { cn } from '@/utils/cn'
import { formatSpeakerDisplayName } from '@/utils/format'

/**
 * Diarization proposes speaker labels; the clinician owns the final role. A human
 * override re-runs clinical structuring so the note reflects the corrected roles.
 */
export function SpeakerRoster({
  speakers,
  editable = false,
  compact = false,
  onChanged,
}: {
  speakers: Speaker[]
  editable?: boolean
  compact?: boolean
  onChanged?: (speaker: Speaker) => void
}) {
  const [busy, setBusy] = useState<string | null>(null)
  const pushToast = useUiStore((state) => state.pushToast)

  const update = async (speaker: Speaker, role: SpeakerRole) => {
    if (role === speaker.role) return
    setBusy(speaker.id)
    try {
      const updated = await api.updateSpeakerRole(speaker.id, role)
      onChanged?.(updated)
      pushToast({
        kind: 'success',
        title: `${speaker.label} set to ${ROLE_STYLES[role].label}`,
        detail: 'Clinical note will re-structure with the updated speaker roles.',
      })
    } catch (error) {
      pushToast({ kind: 'error', title: 'Could not update speaker role', detail: (error as Error).message })
    } finally {
      setBusy(null)
    }
  }

  const body =
    speakers.length === 0 ? (
      <EmptyState title="Listening for voices" detail="Detected participants (Doctor, Patient) will appear here automatically." />
    ) : (
      <ul className={cn('divide-y divide-slate-100 dark:divide-slate-800', compact && 'text-xs')}>
        {speakers.map((speaker) => {
          const role = ROLE_STYLES[speaker.role] ?? ROLE_STYLES.UNKNOWN
          const speakerInfo = formatSpeakerDisplayName(speaker.label, speaker.role, speaker.display_name)
          return (
            <li key={speaker.id} className="flex items-center gap-2.5 px-3.5 py-2.5 hover:bg-slate-50/60 dark:hover:bg-slate-800/50 transition-colors">
              <StatusDot className={role.dot} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs font-bold text-slate-800 dark:text-slate-200">{speakerInfo.title}</p>
                <p className="text-2xs text-slate-500 dark:text-slate-400 font-medium">
                  {speaker.role_source === 'HUMAN' ? 'Custom Assigned' : `Detected ${role.label}`}
                </p>
              </div>
              {editable ? (
                <select
                  value={speaker.role}
                  disabled={busy === speaker.id}
                  onChange={(event) => void update(speaker, event.target.value as SpeakerRole)}
                  className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-2 py-1 text-2xs font-semibold text-slate-700 dark:text-slate-200 shadow-2xs focus:border-teal-500 focus:outline-none"
                  aria-label={`Role for ${speaker.label}`}
                >
                  {SPEAKER_ROLES.map((option) => (
                    <option key={option} value={option}>
                      {ROLE_STYLES[option].label}
                    </option>
                  ))}
                </select>
              ) : (
                <span className={cn('badge rounded-full px-2 py-0.5 text-2xs font-semibold', role.badge)}>
                  {role.label}
                </span>
              )}
            </li>
          )
        })}
      </ul>
    )

  if (compact) return body

  return (
    <Panel title="Participants" icon={<UserCog className="h-3.5 w-3.5 text-teal-600" aria-hidden />} className="shrink-0">
      {body}
    </Panel>
  )
}
