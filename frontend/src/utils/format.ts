/** Formatting helpers shared across the workstation UI. */

export function formatTimestamp(seconds: number | null | undefined): string {
  const total = Math.max(0, Math.floor(seconds ?? 0))
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const secs = total % 60
  return [hours, minutes, secs].map((part) => String(part).padStart(2, '0')).join(':')
}

export function formatDuration(seconds: number | null | undefined): string {
  const total = Math.max(0, Math.round(seconds ?? 0))
  if (total < 60) return `${total}s`
  const minutes = Math.floor(total / 60)
  const secs = total % 60
  if (minutes < 60) return `${minutes}m ${String(secs).padStart(2, '0')}s`
  const hours = Math.floor(minutes / 60)
  return `${hours}h ${String(minutes % 60).padStart(2, '0')}m`
}

export function formatConfidence(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return `${Math.round(value * 100)}%`
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function formatRelative(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  const diffSeconds = Math.round((Date.now() - date.getTime()) / 1000)
  if (diffSeconds < 60) return 'just now'
  if (diffSeconds < 3600) return `${Math.floor(diffSeconds / 60)}m ago`
  if (diffSeconds < 86400) return `${Math.floor(diffSeconds / 3600)}h ago`
  const days = Math.floor(diffSeconds / 86400)
  return days === 1 ? '1 day ago' : `${days} days ago`
}

export function formatLatency(ms: number | null | undefined): string {
  if (!ms) return '—'
  if (ms < 1000) return `${Math.round(ms)} ms`
  return `${(ms / 1000).toFixed(1)} s`
}

export function titleCase(value: string): string {
  return value
    .toLowerCase()
    .split(/[\s_]+/)
    .filter(Boolean)
    .map((word) => word[0].toUpperCase() + word.slice(1))
    .join(' ')
}

export function initials(value: string | null | undefined): string {
  if (!value) return '—'
  return value
    .split(/[\s.@]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('')
}

export function formatSpeakerDisplayName(
  speakerLabel?: string | null,
  role?: string | null,
  customDisplayName?: string | null,
): { title: string; subtitle?: string; fullBadge: string } {
  if (customDisplayName) {
    const roleText = role && role !== 'UNKNOWN' ? titleCase(role) : ''
    return {
      title: customDisplayName,
      subtitle: roleText,
      fullBadge: roleText ? `${customDisplayName} (${roleText})` : customDisplayName,
    }
  }

  let speakerNum = ''
  if (speakerLabel) {
    const match = speakerLabel.match(/(?:speaker[_\s-]*)?(\d+)/i)
    if (match) {
      const idx = parseInt(match[1], 10)
      speakerNum = `Speaker ${idx + 1}`
    } else {
      speakerNum = titleCase(speakerLabel)
    }
  } else {
    speakerNum = 'Speaker'
  }

  const roleText = role && role !== 'UNKNOWN' ? titleCase(role) : ''
  return {
    title: speakerNum,
    subtitle: roleText,
    fullBadge: roleText ? `${speakerNum} (${roleText})` : speakerNum,
  }
}
