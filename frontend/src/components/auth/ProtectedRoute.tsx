import React, { useEffect } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '@/store/authStore'
import { Loader2 } from 'lucide-react'

interface ProtectedRouteProps {
  children: React.ReactNode
  adminOnly?: boolean
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children, adminOnly = false }) => {
  const { token, user, loading, initialized, initAuth } = useAuthStore()
  const location = useLocation()

  useEffect(() => {
    if (!initialized) {
      void initAuth()
    }
  }, [initialized, initAuth])

  if (loading || !initialized) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-slate-900 text-slate-200">
        <Loader2 className="w-8 h-8 animate-spin text-teal-400 mb-3" />
        <p className="text-sm font-medium tracking-wide text-slate-400">Verifying clinical credentials...</p>
      </div>
    )
  }

  if (!token || !user) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  if (adminOnly && user.role !== 'ADMIN') {
    return <Navigate to="/" replace />
  }

  return <>{children}</>
}
