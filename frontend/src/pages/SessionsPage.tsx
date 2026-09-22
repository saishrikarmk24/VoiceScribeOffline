import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { PlusCircle, Trash2 } from 'lucide-react'

import { ConfirmModal, InlineAlert, Panel, Spinner, StatusDot } from '@/components/ui/primitives'
import { NOTE_STATUS_LABELS, SESSION_STATUS_STYLES } from '@/constants'
import { api } from '@/services/api'
import { useUiStore } from '@/store/uiStore'
import type { NoteStatus, SessionStatus, SessionSummary } from '@/types'
import { cn } from '@/utils/cn'
import { formatDateTime, formatDuration } from '@/utils/format'

const STATUS_FILTERS: (SessionStatus | 'ALL')[] = [
  'ALL',
  'CREATED',
  'LIVE',
  'PAUSED',
  'REVIEW',
  'APPROVED',
  'COMPLETED',
]

const PAGE_SIZE = 25

export function SessionsPage() {
  const [items, setItems] = useState<SessionSummary[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [filter, setFilter] = useState<SessionStatus | 'ALL'>('ALL')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [sessionToDelete, setSessionToDelete] = useState<SessionSummary | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [bulkDeleting, setBulkDeleting] = useState(false)
  const [showBulkDeleteModal, setShowBulkDeleteModal] = useState(false)
  const pushToast = useUiStore((state) => state.pushToast)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const page = await api.listSessions({
        limit: PAGE_SIZE,
        offset,
        status: filter === 'ALL' ? undefined : filter,
      })
      setItems(page.items)
      setTotal(page.total)
      setSelectedIds(new Set())
      setError(null)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [filter, offset])

  useEffect(() => {
    void load()
  }, [load])

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  const toggleSelectAll = () => {
    if (selectedIds.size === items.length && items.length > 0) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(items.map((item) => item.id)))
    }
  }

  const confirmDelete = async () => {
    if (!sessionToDelete) return
    setDeleting(true)
    try {
      await api.deleteSession(sessionToDelete.id)
      pushToast({ kind: 'success', title: `${sessionToDelete.reference} deleted` })
      setSessionToDelete(null)
      void load()
    } catch (err) {
      pushToast({ kind: 'error', title: 'Delete failed', detail: (err as Error).message })
    } finally {
      setDeleting(false)
    }
  }

  const confirmBulkDelete = async () => {
    if (selectedIds.size === 0) return
    setBulkDeleting(true)
    try {
      const count = selectedIds.size
      await Promise.all(Array.from(selectedIds).map((id) => api.deleteSession(id)))
      pushToast({ kind: 'success', title: `Deleted ${count} consultation${count > 1 ? 's' : ''}` })
      setSelectedIds(new Set())
      setShowBulkDeleteModal(false)
      void load()
    } catch (err) {
      pushToast({ kind: 'error', title: 'Bulk delete failed', detail: (err as Error).message })
    } finally {
      setBulkDeleting(false)
    }
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-7xl space-y-4 p-5">
        <header className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-lg font-semibold tracking-tight text-slate-900 dark:text-slate-100">Consultation History</h1>
            <p className="text-xs text-slate-500 dark:text-slate-400">{total} consultation record(s).</p>
          </div>
          <Link to="/sessions/new" className="btn-teal flex items-center gap-1.5 shadow-sm">
            <PlusCircle className="h-4 w-4" aria-hidden />
            New Consultation
          </Link>
        </header>

        <div className="flex flex-wrap gap-1.5">
          {STATUS_FILTERS.map((status) => (
            <button
              key={status}
              type="button"
              onClick={() => {
                setFilter(status)
                setOffset(0)
              }}
              className={cn(
                'rounded-full border px-3 py-1 text-2xs font-semibold uppercase tracking-wide transition',
                filter === status
                  ? 'border-teal-600 bg-teal-600 text-white shadow-xs'
                  : 'border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 hover:border-slate-300 dark:hover:border-slate-700',
              )}
            >
              {status === 'ALL' ? 'All Records' : status}
            </button>
          ))}
        </div>

        {/* Floating Bulk Action Bar */}
        {selectedIds.size > 0 ? (
          <div className="flex items-center justify-between rounded-2xl border border-rose-300 dark:border-rose-900/60 bg-rose-100 dark:bg-rose-950/60 px-4 py-2.5 shadow-xs animate-slide-in">
            <span className="text-xs font-bold text-rose-900 dark:text-rose-200">
              {selectedIds.size} consultation{selectedIds.size > 1 ? 's' : ''} selected
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setSelectedIds(new Set())}
                className="rounded-xl border border-rose-300 dark:border-rose-800 bg-white dark:bg-slate-900 px-3 py-1.5 text-xs font-bold text-rose-900 dark:text-rose-200 hover:bg-rose-50 dark:hover:bg-slate-800 transition-colors"
              >
                Deselect All
              </button>
              <button
                type="button"
                onClick={() => setShowBulkDeleteModal(true)}
                className="flex items-center gap-1.5 rounded-xl bg-[#DC2626] px-3.5 py-1.5 text-xs font-bold text-white shadow-xs hover:bg-[#B91C1C] transition-colors"
              >
                <Trash2 className="h-3.5 w-3.5" />
                Delete Selected ({selectedIds.size})
              </button>
            </div>
          </div>
        ) : null}

        {error ? (
          <InlineAlert kind="error" title="Could not load consultations">
            {error}
          </InlineAlert>
        ) : null}

        <Panel title="Consultation Records">
          {loading ? (
            <div className="flex items-center gap-2 p-4 text-xs text-slate-500 dark:text-slate-400">
              <Spinner /> Loading consultations…
            </div>
          ) : items.length === 0 ? (
            <p className="p-4 text-xs text-slate-500 dark:text-slate-400">No consultations match this filter.</p>
          ) : (
            <table className="w-full text-left text-xs">
              <thead className="border-b border-slate-100 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-950/60 text-2xs uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
                <tr>
                  <th className="w-10 px-3 py-2">
                    <input
                      type="checkbox"
                      aria-label="Select all consultations"
                      checked={selectedIds.size === items.length && items.length > 0}
                      onChange={toggleSelectAll}
                      className="h-4 w-4 rounded border-slate-300 text-teal-600 focus:ring-teal-500 cursor-pointer"
                    />
                  </th>
                  <th className="px-3 py-2 font-semibold">Reference</th>
                  <th className="px-3 py-2 font-semibold">Consultation</th>
                  <th className="px-3 py-2 font-semibold">Patient</th>
                  <th className="px-3 py-2 font-semibold">Source</th>
                  <th className="px-3 py-2 font-semibold">Status</th>
                  <th className="px-3 py-2 font-semibold">Note Status</th>
                  <th className="px-3 py-2 text-right font-semibold">Lines</th>
                  <th className="px-3 py-2 text-right font-semibold">Duration</th>
                  <th className="px-3 py-2 text-right font-semibold">Date</th>
                  <th className="px-3 py-2 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {items.map((session) => (
                  <tr
                    key={session.id}
                    className={cn(
                      'transition-colors',
                      selectedIds.has(session.id) ? 'bg-teal-50/40 dark:bg-teal-950/30' : 'hover:bg-slate-50/60 dark:hover:bg-slate-800/40',
                    )}
                  >
                    <td className="px-3 py-2">
                      <input
                        type="checkbox"
                        aria-label={`Select ${session.reference}`}
                        checked={selectedIds.has(session.id)}
                        onChange={() => toggleSelect(session.id)}
                        className="h-4 w-4 rounded border-slate-300 text-teal-600 focus:ring-teal-500 cursor-pointer"
                      />
                    </td>
                    <td className="px-3 py-2">
                      <Link to={`/sessions/${session.id}`} className="mono font-semibold text-teal-700 dark:text-teal-400 hover:underline">
                        {session.reference}
                      </Link>
                    </td>
                    <td className="max-w-[16rem] truncate px-3 py-2 text-slate-800 dark:text-slate-200 font-medium">{session.name}</td>
                    <td className="mono px-3 py-2 text-slate-600 dark:text-slate-400">{session.patient_id}</td>
                    <td className="px-3 py-2 text-slate-600 dark:text-slate-400 capitalize">{session.mode.toLowerCase()}</td>
                    <td className="px-3 py-2">
                      <span className={cn('badge', SESSION_STATUS_STYLES[session.status])}>
                        <StatusDot
                          className={session.status === 'LIVE' ? 'bg-rose-500' : 'bg-current opacity-60'}
                          pulse={session.status === 'LIVE'}
                        />
                        {session.status}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-slate-600 dark:text-slate-400">
                      {session.note_status ? NOTE_STATUS_LABELS[session.note_status as NoteStatus] : '—'}
                    </td>
                    <td className="mono px-3 py-2 text-right text-slate-700 dark:text-slate-300">{session.segment_count}</td>
                    <td className="mono px-3 py-2 text-right text-slate-700 dark:text-slate-300">
                      {formatDuration(session.duration_seconds)}
                    </td>
                    <td className="px-3 py-2 text-right text-slate-500 dark:text-slate-400">{formatDateTime(session.created_at)}</td>
                    <td className="px-3 py-2 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <Link
                          to={session.status === 'LIVE' ? `/sessions/${session.id}/live` : `/sessions/${session.id}/review`}
                          className="btn-secondary !py-0.5 !px-2 text-2xs font-semibold text-teal-700 dark:text-teal-400"
                        >
                          {session.status === 'LIVE' ? 'Open Live' : 'Review Note'}
                        </Link>
                        <button
                          type="button"
                          onClick={() => setSessionToDelete(session)}
                          className="rounded-lg p-1.5 text-slate-400 hover:bg-rose-50 dark:hover:bg-rose-950/50 hover:text-rose-600 dark:hover:text-rose-400 transition-colors"
                          aria-label={`Delete ${session.reference}`}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>

        <ConfirmModal
          open={Boolean(sessionToDelete)}
          title="Delete Consultation?"
          message={`Are you sure you want to delete consultation ${sessionToDelete?.reference}? This permanently removes its transcript, clinical entities, and generated note.`}
          confirmLabel="Delete Record"
          cancelLabel="Cancel"
          tone="danger"
          busy={deleting}
          onConfirm={() => void confirmDelete()}
          onCancel={() => setSessionToDelete(null)}
        />

        <ConfirmModal
          open={showBulkDeleteModal}
          title={`Delete ${selectedIds.size} Consultations?`}
          message={`Are you sure you want to delete the ${selectedIds.size} selected consultation records? This permanently removes their transcripts, clinical entities, and generated notes.`}
          confirmLabel={`Delete ${selectedIds.size} Records`}
          cancelLabel="Cancel"
          tone="danger"
          busy={bulkDeleting}
          onConfirm={() => void confirmBulkDelete()}
          onCancel={() => setShowBulkDeleteModal(false)}
        />

        {total > PAGE_SIZE ? (
          <div className="flex items-center justify-between text-xs text-navy-600">
            <button
              type="button"
              className="btn-secondary"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            >
              Previous
            </button>
            <span className="mono">
              {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total}
            </span>
            <button
              type="button"
              className="btn-secondary"
              disabled={offset + PAGE_SIZE >= total}
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              Next
            </button>
          </div>
        ) : null}
      </div>
    </div>
  )
}
