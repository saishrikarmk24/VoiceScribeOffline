import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Calendar,
  ChevronRight,
  ClipboardList,
  FileCheck2,
  FileText,
  MoreHorizontal,
  Search,
  Sun,
  Users,
} from 'lucide-react'

import { InlineAlert } from '@/components/ui/primitives'
import { MedicalPulseLoader } from '@/components/ui/MedicalAnimations'
import { api } from '@/services/api'
import { useAuthStore } from '@/store/authStore'
import type { DashboardStats } from '@/types'
import { formatDuration, formatRelative } from '@/utils/format'

export function DashboardPage() {
  const { user } = useAuthStore()
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')

  const rawName = user?.full_name || 'Dr. Saksham'
  const doctorName = rawName.startsWith('Dr.') ? rawName : `Dr. ${rawName}`

  // Dynamic greeting based on current time
  const greeting = useMemo(() => {
    const hour = new Date().getHours()
    if (hour < 12) return `Good morning, ${doctorName}`
    if (hour < 18) return `Good afternoon, ${doctorName}`
    return `Good evening, ${doctorName}`
  }, [doctorName])

  // Formatted date string matching screenshot (e.g. Fri, 12 Sep 2026)
  const currentDateFormatted = useMemo(() => {
    return new Intl.DateTimeFormat('en-GB', {
      weekday: 'short',
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    }).format(new Date())
  }, [])

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const nextStats = await api.dashboard()
        if (cancelled) return
        setStats(nextStats)
        setError(null)
      } catch (err) {
        if (!cancelled) setError((err as Error).message)
      }
    }
    void load()
    const timer = window.setInterval(load, 15000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [])

  // Recent consultation records: real sessions if present, or demo sessions matching the screenshot
  const consultations = useMemo(() => {
    const source =
      stats?.recent_sessions && stats.recent_sessions.length > 0
        ? stats.recent_sessions
        : [
            {
              id: 'demo-1',
              reference: 'SIM-2026-018',
              name: 'Outpatient Consultation',
              status: 'CREATED',
              note_status: 'DRAFT',
              segment_count: 0,
              entity_count: 0,
              duration_seconds: 0,
              created_at: new Date(Date.now() - 6 * 3600 * 1000).toISOString(),
            },
            {
              id: 'demo-2',
              reference: 'SIM-2026-017',
              name: 'Follow-up Consultation',
              status: 'COMPLETED',
              note_status: 'APPROVED',
              segment_count: 124,
              entity_count: 8,
              duration_seconds: 754,
              created_at: new Date(Date.now() - 24 * 3600 * 1000).toISOString(),
            },
            {
              id: 'demo-3',
              reference: 'SIM-2026-016',
              name: 'Teleconsultation',
              status: 'COMPLETED',
              note_status: 'APPROVED',
              segment_count: 98,
              entity_count: 6,
              duration_seconds: 561,
              created_at: new Date(Date.now() - 48 * 3600 * 1000).toISOString(),
            },
            {
              id: 'demo-4',
              reference: 'SIM-2026-015',
              name: 'New Patient Visit',
              status: 'COMPLETED',
              note_status: 'APPROVED',
              segment_count: 142,
              entity_count: 10,
              duration_seconds: 902,
              created_at: new Date(Date.now() - 72 * 3600 * 1000).toISOString(),
            },
          ]

    if (!search.trim()) return source
    const query = search.toLowerCase()
    return source.filter(
      (session) =>
        session.reference.toLowerCase().includes(query) ||
        session.name.toLowerCase().includes(query) ||
        session.status.toLowerCase().includes(query),
    )
  }, [stats?.recent_sessions, search])

  if (error && !stats) {
    return (
      <div className="p-6 animate-fade-in-up">
        <InlineAlert kind="error" title="Backend unreachable">
          {error}. Start the API with <code className="mono">uvicorn app.main:app --reload</code> in{' '}
          <code className="mono">backend/</code>.
        </InlineAlert>
      </div>
    )
  }

  if (!stats) {
    return (
      <div className="flex h-full items-center justify-center p-12">
        <MedicalPulseLoader
          label="Connecting to Clinical Informatics..."
          sublabel="Aggregating ambulatory metrics, consultation logs, and encounter analytics"
        />
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto bg-[#f8fafc] dark:bg-slate-950 text-slate-900 dark:text-slate-100 p-5 md:p-6 lg:p-8 space-y-6 animate-fade-in-up transition-colors duration-200">
      <div className="mx-auto max-w-7xl space-y-6">
        {/* Top Header Bar */}
        <header className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="flex items-center gap-3.5">
            <div className="grid place-items-center shrink-0">
              <Sun className="h-7 w-7 text-amber-500 fill-amber-400" />
            </div>
            <div>
              <h1 className="text-xl md:text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
                {greeting}
              </h1>
              <p className="text-xs md:text-sm font-medium text-slate-500 dark:text-slate-400 mt-0.5">
                Here's an overview of your consultations today.
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {/* Search Input */}
            <div className="relative">
              <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search consultations, patients..."
                className="w-56 sm:w-64 pl-9 pr-3.5 py-2 bg-slate-50/80 dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 rounded-xl text-xs text-slate-800 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-teal-500/20 focus:border-teal-500 shadow-2xs transition-all"
              />
            </div>

            {/* Date Pill */}
            <div className="inline-flex items-center gap-2 bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 rounded-xl px-3.5 py-2 text-xs font-medium text-slate-700 dark:text-slate-200 shadow-2xs">
              <Calendar className="h-4 w-4 text-slate-400" />
              <span>{currentDateFormatted}</span>
            </div>
          </div>
        </header>

        {/* 4 Stat Cards Row */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5 lg:gap-6">
          {/* Card 1: Active Encounters */}
          <div className="rounded-2xl border border-[#bbf7d0]/60 dark:border-teal-800/40 bg-[#ecfdf5] dark:bg-teal-950/30 p-5 shadow-2xs transition-all hover:shadow-xs">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3.5">
                <div className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-[#ccfbf1] dark:bg-teal-900/60 text-[#0d9488] dark:text-teal-300 shadow-2xs">
                  <Users className="h-5 w-5" />
                </div>
                <div>
                  <p className="text-xs font-semibold text-slate-700 dark:text-slate-300">Active Encounters</p>
                  <p className="text-2xl font-bold text-slate-900 dark:text-white mt-0.5 leading-tight">
                    {stats.active_sessions}
                  </p>
                </div>
              </div>
              <Link
                to="/sessions?status=LIVE"
                className="grid h-6 w-6 place-items-center rounded-full bg-white dark:bg-slate-800 text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 shadow-2xs border border-slate-100 dark:border-slate-700/50 transition-colors"
              >
                <ChevronRight className="h-3.5 w-3.5" />
              </Link>
            </div>
            <div className="mt-3.5 flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400 font-medium">
              <span className="h-2 w-2 rounded-full bg-emerald-500 shrink-0" />
              <span>Live or in progress</span>
            </div>
          </div>

          {/* Card 2: Pending Review */}
          <div className="rounded-2xl border border-[#fecdd3]/60 dark:border-rose-800/40 bg-[#fff1f2] dark:bg-rose-950/30 p-5 shadow-2xs transition-all hover:shadow-xs">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3.5">
                <div className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-[#ffe4e6] dark:bg-rose-900/60 text-rose-600 dark:text-rose-300 shadow-2xs">
                  <FileText className="h-5 w-5" />
                </div>
                <div>
                  <p className="text-xs font-semibold text-slate-700 dark:text-slate-300">Pending Review</p>
                  <p className="text-2xl font-bold text-slate-900 dark:text-white mt-0.5 leading-tight">
                    {stats.review_required_count}
                  </p>
                </div>
              </div>
              <Link
                to="/sessions"
                className="grid h-6 w-6 place-items-center rounded-full bg-white dark:bg-slate-800 text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 shadow-2xs border border-slate-100 dark:border-slate-700/50 transition-colors"
              >
                <ChevronRight className="h-3.5 w-3.5" />
              </Link>
            </div>
            <div className="mt-3.5 flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400 font-medium">
              <span className="h-2 w-2 rounded-full bg-rose-500 shrink-0" />
              <span>Doctor sign-off needed</span>
            </div>
          </div>

          {/* Card 3: Notes Generated */}
          <div className="rounded-2xl border border-[#fde68a]/60 dark:border-amber-800/40 bg-[#fffbeb] dark:bg-amber-950/30 p-5 shadow-2xs transition-all hover:shadow-xs">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3.5">
                <div className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-[#fef3c7] dark:bg-amber-900/60 text-amber-600 dark:text-amber-300 shadow-2xs">
                  <FileCheck2 className="h-5 w-5" />
                </div>
                <div>
                  <p className="text-xs font-semibold text-slate-700 dark:text-slate-300">Notes Generated</p>
                  <p className="text-2xl font-bold text-slate-900 dark:text-white mt-0.5 leading-tight">
                    {stats.notes_generated}
                  </p>
                </div>
              </div>
              <Link
                to="/sessions"
                className="grid h-6 w-6 place-items-center rounded-full bg-white dark:bg-slate-800 text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 shadow-2xs border border-slate-100 dark:border-slate-700/50 transition-colors"
              >
                <ChevronRight className="h-3.5 w-3.5" />
              </Link>
            </div>
            <div className="mt-3.5 flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400 font-medium">
              <span className="h-2 w-2 rounded-full bg-amber-500 shrink-0" />
              <span>{stats.notes_approved} signed &amp; approved</span>
            </div>
          </div>

          {/* Card 4: Total Encounters */}
          <div className="rounded-2xl border border-[#ddd6fe]/60 dark:border-purple-800/40 bg-[#f5f3ff] dark:bg-purple-950/30 p-5 shadow-2xs transition-all hover:shadow-xs">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3.5">
                <div className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-[#ede9fe] dark:bg-purple-900/60 text-purple-600 dark:text-purple-300 shadow-2xs">
                  <ClipboardList className="h-5 w-5" />
                </div>
                <div>
                  <p className="text-xs font-semibold text-slate-700 dark:text-slate-300">Total Encounters</p>
                  <p className="text-2xl font-bold text-slate-900 dark:text-white mt-0.5 leading-tight">
                    {stats.total_sessions || stats.completed_sessions}
                  </p>
                </div>
              </div>
              <Link
                to="/sessions"
                className="grid h-6 w-6 place-items-center rounded-full bg-white dark:bg-slate-800 text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 shadow-2xs border border-slate-100 dark:border-slate-700/50 transition-colors"
              >
                <ChevronRight className="h-3.5 w-3.5" />
              </Link>
            </div>
            <div className="mt-3.5 flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400 font-medium">
              <span className="h-2 w-2 rounded-full bg-purple-500 shrink-0" />
              <span>All time</span>
            </div>
          </div>
        </div>

        {/* Recent Consultations Card & Table */}
        <div className="rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-2xs overflow-hidden">
          {/* Card Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 dark:border-slate-800/80">
            <div className="flex items-center gap-3">
              <div className="grid h-9 w-9 place-items-center rounded-xl bg-emerald-50 dark:bg-emerald-950/50 text-emerald-600 dark:text-emerald-400">
                <FileText className="h-5 w-5" />
              </div>
              <div>
                <h2 className="text-base font-bold text-slate-900 dark:text-slate-100 leading-tight">
                  Recent Consultations
                </h2>
                <p className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">
                  Your latest consultation records
                </p>
              </div>
            </div>
            <Link
              to="/sessions"
              className="inline-flex items-center gap-1 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3.5 py-1.5 text-xs font-semibold text-slate-700 dark:text-slate-300 hover:text-teal-600 dark:hover:text-teal-400 hover:border-teal-300 transition-colors shadow-2xs"
            >
              <span>View all</span>
              <ChevronRight className="h-3.5 w-3.5" />
            </Link>
          </div>

          {/* Table Container */}
          <div className="overflow-x-auto">
            <table className="w-full table-fixed text-left text-xs">
              <colgroup>
                <col className="w-[15%]" />
                <col className="w-[23%]" />
                <col className="w-[12%]" />
                <col className="w-[14%]" />
                <col className="w-[10%]" />
                <col className="w-[8%]" />
                <col className="w-[9%]" />
                <col className="w-[9%]" />
                <col className="w-[4%]" />
              </colgroup>
              <thead className="bg-slate-50/70 dark:bg-slate-950/60 text-2xs uppercase tracking-wider font-semibold text-slate-400 dark:text-slate-500 border-b border-slate-100 dark:border-slate-800">
                <tr>
                  <th className="pl-6 pr-3 py-3.5 font-semibold">Reference</th>
                  <th className="px-3 py-3.5 font-semibold">Consultation</th>
                  <th className="px-3 py-3.5 font-semibold">Status</th>
                  <th className="px-3 py-3.5 font-semibold">Note Status</th>
                  <th className="px-3 py-3.5 font-semibold text-center">Speech Lines</th>
                  <th className="px-3 py-3.5 font-semibold text-center">Findings</th>
                  <th className="px-3 py-3.5 font-semibold text-center">Duration</th>
                  <th className="px-3 py-3.5 font-semibold text-left">Date</th>
                  <th className="pl-2 pr-6 py-3.5 text-right"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800/80">
                {consultations.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="px-6 py-10 text-center text-xs text-slate-400">
                      No matching consultation records found.
                    </td>
                  </tr>
                ) : (
                  consultations.map((session) => (
                    <tr
                      key={session.id}
                      className="hover:bg-slate-50/70 dark:hover:bg-slate-800/40 transition-colors"
                    >
                      {/* Reference Link */}
                      <td className="pl-6 pr-3 py-3.5 font-semibold">
                        <Link
                          to={`/sessions/${session.id}/review`}
                          className="font-semibold text-teal-600 dark:text-teal-400 hover:underline"
                        >
                          {session.reference}
                        </Link>
                      </td>

                      {/* Consultation Name */}
                      <td className="px-3 py-3.5 text-slate-800 dark:text-slate-200 font-medium truncate">
                        {session.name}
                      </td>

                      {/* Encounter Status Badge */}
                      <td className="px-3 py-3.5">
                        {session.status === 'COMPLETED' ||
                        session.status === 'APPROVED' ||
                        session.note_status === 'APPROVED' ||
                        session.note_status === 'EXPORTED' ||
                        session.note_status === 'SIGNED' ? (
                          <span className="inline-flex items-center gap-1.5 rounded-full px-3 py-0.5 text-xs font-semibold bg-[#dcfce7] text-[#16a34a] border border-[#bbf7d0] dark:bg-emerald-950/60 dark:text-emerald-300 dark:border-emerald-800/50">
                            <span className="h-1.5 w-1.5 rounded-full bg-[#16a34a] dark:bg-emerald-400" />
                            Completed
                          </span>
                        ) : session.status === 'LIVE' ? (
                          <span className="inline-flex items-center gap-1.5 rounded-full px-3 py-0.5 text-xs font-semibold bg-[#ffe4e6] text-[#e11d48] border border-[#fecdd3] dark:bg-rose-950/60 dark:text-rose-300 dark:border-rose-800/50">
                            <span className="h-1.5 w-1.5 rounded-full bg-[#e11d48] animate-pulse" />
                            Live
                          </span>
                        ) : session.status === 'PAUSED' ? (
                          <span className="inline-flex items-center gap-1.5 rounded-full px-3 py-0.5 text-xs font-semibold bg-[#fef3c7] text-[#b45309] border border-[#fde68a] dark:bg-amber-950/60 dark:text-amber-300 dark:border-amber-800/50">
                            <span className="h-1.5 w-1.5 rounded-full bg-[#b45309]" />
                            Paused
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 rounded-full px-3 py-0.5 text-xs font-semibold bg-[#e0f2fe] text-[#0284c7] border border-[#bae6fd] dark:bg-sky-950/60 dark:text-sky-300 dark:border-sky-800/50">
                            <span className="h-1.5 w-1.5 rounded-full bg-[#0284c7]" />
                            Created
                          </span>
                        )}
                      </td>

                      {/* Note Status Badge */}
                      <td className="px-3 py-3.5">
                        {session.note_status === 'APPROVED' ||
                        session.note_status === 'SIGNED' ||
                        session.note_status === 'EXPORTED' ? (
                          <span className="inline-flex items-center gap-1.5 rounded-full px-3 py-0.5 text-xs font-semibold bg-[#dcfce7] text-[#16a34a] border border-[#bbf7d0] dark:bg-emerald-950/60 dark:text-emerald-300 dark:border-emerald-800/50">
                            <span className="h-1.5 w-1.5 rounded-full bg-[#16a34a] dark:bg-emerald-400" />
                            Signed
                          </span>
                        ) : session.note_status === 'REVIEW_REQUIRED' ? (
                          <span className="inline-flex items-center gap-1.5 rounded-full px-3 py-0.5 text-xs font-semibold bg-[#fef3c7] text-[#b45309] border border-[#fde68a] dark:bg-amber-950/60 dark:text-amber-300 dark:border-amber-800/50">
                            <span className="h-1.5 w-1.5 rounded-full bg-[#b45309]" />
                            Review Needed
                          </span>
                        ) : session.note_status === 'DRAFT' ? (
                          <span className="text-slate-500 dark:text-slate-400 font-medium text-xs">Draft Note</span>
                        ) : (
                          <span className="text-slate-500 dark:text-slate-400 font-medium text-xs">Drafting Note</span>
                        )}
                      </td>

                      {/* Speech Lines */}
                      <td className="px-3 py-3.5 text-center font-medium text-slate-700 dark:text-slate-300">
                        {session.segment_count || 0}
                      </td>

                      {/* Findings */}
                      <td className="px-3 py-3.5 text-center font-medium text-slate-700 dark:text-slate-300">
                        {session.entity_count || 0}
                      </td>

                      {/* Duration */}
                      <td className="px-3 py-3.5 text-center font-medium text-slate-700 dark:text-slate-300">
                        {formatDuration(session.duration_seconds)}
                      </td>

                      {/* Date */}
                      <td className="px-3 py-3.5 text-left font-medium text-slate-500 dark:text-slate-400">
                        {formatRelative(session.created_at)}
                      </td>

                      {/* Action Menu */}
                      <td className="pl-2 pr-6 py-3.5 text-right">
                        <Link
                          to={`/sessions/${session.id}/review`}
                          className="inline-grid h-7 w-7 place-items-center rounded-lg text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                          title="View consultation"
                        >
                          <MoreHorizontal className="h-4 w-4" />
                        </Link>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  )
}
