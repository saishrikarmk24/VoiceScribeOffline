import { create } from 'zustand'
import { api, setIdentity } from '@/services/api'
import type { AuthUser } from '@/types'

export type { AuthUser }

interface AuthState {
  token: string | null
  user: AuthUser | null
  loading: boolean
  initialized: boolean
  setAuth: (token: string, user: AuthUser) => void
  logout: () => void
  initAuth: () => Promise<void>
}

const TOKEN_KEY = 'medscribe_auth_token'
const USER_KEY = 'medscribe_auth_user'

export const useAuthStore = create<AuthState>((set, get) => ({
  token: null,
  user: null,
  loading: true,
  initialized: false,

  setAuth: (token: string, user: AuthUser) => {
    localStorage.setItem(TOKEN_KEY, token)
    localStorage.setItem(USER_KEY, JSON.stringify(user))
    setIdentity({
      token,
      email: user.email,
      role: user.role,
      doctor_id: user.doctor_id || undefined,
    })
    set({ token, user, loading: false, initialized: true })
  },

  logout: () => {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
    setIdentity({})
    set({ token: null, user: null, loading: false, initialized: true })
  },

  initAuth: async () => {
    const savedToken = localStorage.getItem(TOKEN_KEY)
    const savedUser = localStorage.getItem(USER_KEY)

    if (savedToken && savedUser) {
      try {
        const parsedUser = JSON.parse(savedUser) as AuthUser
        setIdentity({
          token: savedToken,
          email: parsedUser.email,
          role: parsedUser.role,
          doctor_id: parsedUser.doctor_id || undefined,
        })
        set({ token: savedToken, user: parsedUser, loading: false, initialized: true })

        // Validate token with backend asynchronously
        try {
          const freshUser = await api.getMe()
          if (freshUser) {
            localStorage.setItem(USER_KEY, JSON.stringify(freshUser))
            set({ user: freshUser as AuthUser })
          }
        } catch {
          // If token expired, log out
          get().logout()
        }
        return
      } catch {
        get().logout()
      }
    } else {
      set({ token: null, user: null, loading: false, initialized: true })
    }
  },
}))
