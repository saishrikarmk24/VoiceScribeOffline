import { useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import {
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  HelpCircle,
  LayoutDashboard,
  LogOut,
  Moon,
  PlusCircle,
  Sun,
  Users,
  X,
} from 'lucide-react'

import { SAFETY_NOTICE } from '@/constants'
import { useAuthStore } from '@/store/authStore'
import { useUiStore } from '@/store/uiStore'
import { cn } from '@/utils/cn'
import { initials } from '@/utils/format'

const BASE_NAV = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/sessions/new', label: 'New Consultation', icon: PlusCircle, end: false },
  // Temporarily hidden from public view - can be reactivated later:
  // { to: '/sessions/gmeet', label: 'Record Google Meet', icon: Video, end: false },
  { to: '/sessions', label: 'Consultations', icon: ClipboardList, end: true },
]

export function AppLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const { user, logout } = useAuthStore()
  const { theme, toggleTheme } = useUiStore()
  const [collapsed, setCollapsed] = useState(false)
  const [showHelpModal, setShowHelpModal] = useState(false)

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const rawDisplayName = user?.full_name || 'Dr. Saksham'
  const displayName = rawDisplayName.startsWith('Dr.') ? rawDisplayName : `Dr. ${rawDisplayName}`
  const department = user?.department || 'Pediatrics'
  const doctorId = user?.doctor_id

  const navItems = [...BASE_NAV]
  if (user?.role === 'ADMIN') {
    navItems.push({
      to: '/admin/doctors',
      label: 'Doctor Admin',
      icon: Users,
      end: false,
    })
  }

  return (
    <div className="flex h-full min-h-0 bg-[#f8fafc] dark:bg-slate-950 overflow-hidden font-sans transition-colors duration-200">
      {/* Sleek light clinical sidebar matching screenshot */}
      <aside
        className={cn(
          'flex shrink-0 flex-col justify-between bg-white dark:bg-slate-900 border-r border-slate-200/80 dark:border-slate-800 text-slate-800 dark:text-slate-100 p-4 shadow-2xs transition-all duration-200 ease-in-out z-20',
          collapsed ? 'w-18' : 'w-64',
        )}
      >
        <div>
          {/* Top Branding / Toggle */}
          <div
            className={cn(
              'flex items-center pb-3.5 mb-4 border-b border-slate-100 dark:border-slate-800',
              collapsed ? 'justify-center' : 'justify-between',
            )}
          >
            {!collapsed ? (
              <div className="flex items-center overflow-hidden">
                <img
                  src="/sims-logo.png"
                  alt="SIMS VoiceScribe AI"
                  className="dark:hidden h-9 w-auto max-w-[185px] object-contain"
                />
                <img
                  src="/sims-logo-dark.png"
                  alt="SIMS VoiceScribe AI"
                  className="hidden dark:block h-9 w-auto max-w-[185px] object-contain"
                />
              </div>
            ) : null}
            <button
              type="button"
              onClick={() => setCollapsed(!collapsed)}
              className="rounded-full p-1.5 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-700 dark:hover:text-slate-200 transition-colors"
              aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
              title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            >
              {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
            </button>
          </div>

          {/* Primary Navigation */}
          <nav className="space-y-1">
            {navItems.map(({ to, label, icon: Icon, end }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                title={collapsed ? label : undefined}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-3 rounded-2xl px-3.5 py-2.5 text-xs font-semibold transition-all duration-150',
                    isActive
                      ? 'bg-[#e6f7f4] text-[#0d9488] dark:bg-teal-950/60 dark:text-teal-300 shadow-2xs'
                      : 'text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800/60 hover:text-slate-900 dark:hover:text-slate-200',
                    collapsed && 'justify-center px-0 py-3',
                  )
                }
              >
                <Icon className="h-4 w-4 shrink-0" aria-hidden />
                {!collapsed ? <span className="truncate">{label}</span> : null}
              </NavLink>
            ))}
          </nav>
        </div>

        {/* Bottom Navigation & Profile */}
        <div className="space-y-2 pt-3">
          <div className="space-y-1">
            <button
              type="button"
              onClick={() => setShowHelpModal(true)}
              title={collapsed ? 'Help & Support' : undefined}
              className={cn(
                'flex w-full items-center gap-3 rounded-2xl px-3.5 py-2 text-xs font-medium text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-slate-200 transition-colors',
                collapsed && 'justify-center px-0',
              )}
            >
              <HelpCircle className="h-4 w-4 shrink-0" />
              {!collapsed ? <span>Help &amp; Support</span> : null}
            </button>
          </div>

          {/* User Profile Card */}
          <div
            className={cn(
              'rounded-2xl border border-slate-200/70 dark:border-slate-700/60 bg-slate-50/70 dark:bg-slate-800/50 p-2.5 transition-all',
              collapsed ? 'flex justify-center p-2' : 'flex items-center justify-between gap-2',
            )}
          >
            <div className="flex items-center gap-2.5 overflow-hidden">
              <span
                className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-teal-100 text-teal-800 dark:bg-teal-950 dark:text-teal-200 font-bold text-xs"
                title={`${displayName} (${department})`}
              >
                {initials(displayName) || 'SS'}
              </span>
              {!collapsed ? (
                <div className="min-w-0 leading-tight">
                  <p className="truncate text-xs font-bold text-slate-900 dark:text-slate-100">{displayName}</p>
                  <p className="truncate text-2xs font-medium text-slate-500 dark:text-slate-400 mt-0.5">
                    {department}{doctorId ? ` • ${doctorId}` : ''}
                  </p>
                </div>
              ) : null}
            </div>
            {!collapsed ? <ChevronRight className="h-4 w-4 text-slate-400 shrink-0" /> : null}
          </div>

          {/* Sign Out and Theme Toggle */}
          <div className={cn('flex items-center pt-1', collapsed ? 'flex-col gap-2' : 'justify-between')}>
            <button
              type="button"
              onClick={handleLogout}
              className="inline-flex items-center gap-2 text-xs font-medium text-slate-500 dark:text-slate-400 hover:text-rose-600 dark:hover:text-rose-400 transition-colors px-1 py-1 rounded-lg"
              title="Sign out"
            >
              <LogOut className="h-4 w-4" />
              {!collapsed ? <span>Sign out</span> : null}
            </button>

            <button
              type="button"
              onClick={toggleTheme}
              className="p-1.5 rounded-xl text-slate-400 hover:text-amber-500 hover:bg-amber-500/10 transition-colors"
              title={theme === 'dark' ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
            >
              {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex min-w-0 flex-1 flex-col bg-[#f8fafc] dark:bg-slate-950 overflow-hidden text-slate-900 dark:text-slate-100 transition-colors duration-200">
        <main className="min-h-0 flex-1 overflow-hidden">
          <div key={location.pathname} className="h-full w-full min-h-0 animate-fade-in-up">
            <Outlet />
          </div>
        </main>
        {location.pathname !== '/' && (
          <footer className="border-t border-slate-200/60 dark:border-slate-800 bg-white/70 dark:bg-slate-900/70 px-5 py-2 text-2xs text-slate-400 dark:text-slate-500 flex items-center justify-between shrink-0">
            <span>{SAFETY_NOTICE}</span>
            <span className="font-semibold text-slate-500 dark:text-slate-400">SIMS Hospital Clinical Informatics</span>
          </footer>
        )}
      </div>

      {/* Help & Support Modal */}
      {showHelpModal ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4 animate-fade-in">
          <div className="relative w-full max-w-md rounded-3xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-6 shadow-xl animate-scale-spring text-slate-800 dark:text-slate-100">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100 dark:border-slate-800">
              <div className="flex items-center gap-2.5">
                <div className="grid h-8 w-8 place-items-center rounded-xl bg-teal-50 dark:bg-teal-950/60 text-teal-600 dark:text-teal-400">
                  <HelpCircle className="h-4 w-4" />
                </div>
                <h3 className="text-sm font-bold">Help &amp; Clinical Support</h3>
              </div>
              <button
                type="button"
                onClick={() => setShowHelpModal(false)}
                className="p-1 rounded-full text-slate-400 hover:text-slate-600 hover:bg-slate-100 dark:hover:bg-slate-800"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="mt-4 space-y-3 text-xs leading-relaxed text-slate-600 dark:text-slate-300">
              <p>
                <strong>SIMS MedScribe</strong> provides ambient multi-lingual speech transcription, 13-particular
                Ambulatory Care clinical structuring, and official hospital-grade documentation.
              </p>
              <div className="rounded-2xl bg-slate-50 dark:bg-slate-800/60 p-3 space-y-1.5 border border-slate-200/60 dark:border-slate-700/60 text-2xs">
                <p className="font-bold text-slate-800 dark:text-slate-200">Department of Clinical Informatics</p>
                <p>SIMS Hospital, Jawaharlal Nehru Salai, Vadapalani, Chennai</p>
                <p>Support Hotline: ext. 4401 | Email: support@simshospital.com</p>
              </div>
              <p className="text-2xs text-slate-400">
                All generated clinical notes require physician review and verification prior to EHR sign-off.
              </p>
            </div>
            <div className="mt-5 flex justify-end">
              <button
                type="button"
                onClick={() => setShowHelpModal(false)}
                className="rounded-xl bg-teal-600 hover:bg-teal-700 text-white font-semibold text-xs px-4 py-2 transition-colors shadow-xs"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
