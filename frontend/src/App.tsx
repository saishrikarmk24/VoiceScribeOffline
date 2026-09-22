import { useEffect } from 'react'
import { Route, Routes } from 'react-router-dom'

import { AppLayout } from '@/components/layout/AppLayout'
import { ProtectedRoute } from '@/components/auth/ProtectedRoute'
import { ToastHost } from '@/components/ui/ToastHost'
import { AdminDoctorsPage } from '@/pages/AdminDoctorsPage'
import { DashboardPage } from '@/pages/DashboardPage'
import { GMeetRecordPage } from '@/pages/GMeetRecordPage'
import { LiveSessionPage } from '@/pages/LiveSessionPage'
import { LoginPage } from '@/pages/LoginPage'
import { NewSessionPage } from '@/pages/NewSessionPage'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { ReviewPage } from '@/pages/ReviewPage'
import { SessionDetailPage } from '@/pages/SessionDetailPage'
import { SessionsPage } from '@/pages/SessionsPage'
import { SettingsPage } from '@/pages/SettingsPage'
import { useAuthStore } from '@/store/authStore'

export function App() {
  const initAuth = useAuthStore((s) => s.initAuth)

  useEffect(() => {
    void initAuth()
  }, [initAuth])

  return (
    <>
      <Routes>
        <Route path="/login" element={<LoginPage />} />

        <Route
          element={
            <ProtectedRoute>
              <AppLayout />
            </ProtectedRoute>
          }
        >
          <Route path="/" element={<DashboardPage />} />
          <Route path="/sessions" element={<SessionsPage />} />
          <Route path="/sessions/new" element={<NewSessionPage />} />
          <Route path="/sessions/gmeet" element={<GMeetRecordPage />} />
          <Route path="/sessions/:id" element={<SessionDetailPage />} />
          <Route path="/sessions/:id/live" element={<LiveSessionPage />} />
          <Route path="/sessions/:id/review" element={<ReviewPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route
            path="/admin/doctors"
            element={
              <ProtectedRoute adminOnly>
                <AdminDoctorsPage />
              </ProtectedRoute>
            }
          />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
      <ToastHost />
    </>
  )
}
