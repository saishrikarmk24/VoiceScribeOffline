import { create } from 'zustand'

import { setIdentity } from '@/services/api'

export type ToastKind = 'info' | 'success' | 'warning' | 'error'

export interface Toast {
  id: string
  kind: ToastKind
  title: string
  detail?: string
}

export type Theme = 'dark' | 'light'

interface UiState {
  identityEmail: string
  identityRole: string
  identityName: string
  theme: Theme
  toasts: Toast[]
  setIdentity: (email: string, role: string, name: string) => void
  setTheme: (theme: Theme) => void
  toggleTheme: () => void
  pushToast: (toast: Omit<Toast, 'id'>) => void
  dismissToast: (id: string) => void
}

const STORAGE_KEY = 'medscribe.identity'
const THEME_STORAGE_KEY = 'medscribe.theme'

function loadTheme(): Theme {
  if (typeof localStorage === 'undefined') return 'dark'
  const saved = localStorage.getItem(THEME_STORAGE_KEY)
  return saved === 'light' ? 'light' : 'dark' // default to dark
}

function applyTheme(theme: Theme): void {
  if (typeof document !== 'undefined') {
    if (theme === 'dark') {
      document.documentElement.classList.add('dark')
    } else {
      document.documentElement.classList.remove('dark')
    }
  }
}

const initialTheme = loadTheme()
applyTheme(initialTheme)

function loadIdentity(): { email: string; role: string; name: string } {
  if (typeof localStorage === 'undefined') {
    return { email: 'dev.clinician@medscribe.local', role: 'DOCTOR', name: 'Dev Clinician' }
  }
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) return JSON.parse(raw) as { email: string; role: string; name: string }
  } catch {
    /* fall through to the default development identity */
  }
  return { email: 'dev.clinician@medscribe.local', role: 'DOCTOR', name: 'Dev Clinician' }
}

const stored = loadIdentity()
setIdentity({ email: stored.email, role: stored.role })

export const useUiStore = create<UiState>((set, get) => ({
  identityEmail: stored.email,
  identityRole: stored.role,
  identityName: stored.name,
  theme: initialTheme,
  toasts: [],

  setTheme: (theme) => {
    applyTheme(theme)
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem(THEME_STORAGE_KEY, theme)
    }
    set({ theme })
  },

  toggleTheme: () => {
    const next = get().theme === 'dark' ? 'light' : 'dark'
    get().setTheme(next)
  },

  setIdentity: (email, role, name) => {
    setIdentity({ email, role })
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ email, role, name }))
    }
    set({ identityEmail: email, identityRole: role, identityName: name })
  },

  pushToast: (toast) => {
    const id = Math.random().toString(36).slice(2, 9)
    set({ toasts: [...get().toasts, { ...toast, id }] })
    if (typeof window !== 'undefined') {
      window.setTimeout(() => get().dismissToast(id), toast.kind === 'error' ? 8000 : 4500)
    }
  },

  dismissToast: (id) => set({ toasts: get().toasts.filter((toast) => toast.id !== id) }),
}))
