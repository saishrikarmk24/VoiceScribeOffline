import React, { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import {
  Stethoscope,
  ShieldCheck,
  Lock,
  Mail,
  User,
  AlertCircle,
  Building2,
  ChevronRight,
  KeyRound,
  ShieldAlert,
  Loader2,
} from 'lucide-react'
import { api } from '@/services/api'
import { useAuthStore } from '@/store/authStore'

export function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const { setAuth } = useAuthStore()

  const [activeTab, setActiveTab] = useState<'DOCTOR' | 'ADMIN'>('DOCTOR')
  const [isAdminSetup, setIsAdminSetup] = useState<boolean>(false)

  // Doctor credentials
  const [doctorIdentifier, setDoctorIdentifier] = useState('')
  const [doctorPassword, setDoctorPassword] = useState('')

  // Admin credentials
  const [adminEmail, setAdminEmail] = useState('')
  const [adminFullName, setAdminFullName] = useState('')
  const [adminPassword, setAdminPassword] = useState('')
  const [adminConfirmPassword, setAdminConfirmPassword] = useState('')

  // UI status
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  const redirectAfterLogin = (role: string) => {
    const from = (location.state as { from?: { pathname: string } })?.from?.pathname
    if (from && from !== '/login') {
      navigate(from, { replace: true })
    } else if (role === 'ADMIN') {
      navigate('/admin/doctors', { replace: true })
    } else {
      navigate('/', { replace: true })
    }
  }

  const handleDoctorLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setSuccessMessage(null)

    if (!doctorIdentifier.trim() || !doctorPassword) {
      setError('Please provide your Doctor ID or registered email and password.')
      return
    }

    setLoading(true)
    try {
      const resp = await api.login(doctorIdentifier.trim(), doctorPassword)
      setAuth(resp.token, resp.user)
      redirectAfterLogin(resp.user.role)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Authentication failed. Please verify credentials.')
    } finally {
      setLoading(false)
    }
  }

  const handleAdminLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setSuccessMessage(null)

    if (!adminEmail.trim() || !adminPassword) {
      setError('Please provide administrator email and password.')
      return
    }

    setLoading(true)
    try {
      const resp = await api.login(adminEmail.trim(), adminPassword)
      if (resp.user.role !== 'ADMIN') {
        setError('This portal is reserved for Hospital Administrators.')
        return
      }
      setAuth(resp.token, resp.user)
      redirectAfterLogin('ADMIN')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Administrator authentication failed.')
    } finally {
      setLoading(false)
    }
  }

  const handleAdminSetup = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setSuccessMessage(null)

    if (!adminEmail.trim() || !adminFullName.trim() || !adminPassword) {
      setError('All fields are required to initialize the administrator account.')
      return
    }
    if (adminPassword.length < 8) {
      setError('Administrator password must contain at least 8 characters.')
      return
    }
    if (adminPassword !== adminConfirmPassword) {
      setError('Passwords do not match.')
      return
    }

    setLoading(true)
    try {
      const resp = await api.adminRegister({
        email: adminEmail.trim(),
        full_name: adminFullName.trim(),
        password: adminPassword,
      })
      setSuccessMessage('Administrator account initialized successfully.')
      setAuth(resp.token, resp.user)
      redirectAfterLogin('ADMIN')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Admin setup failed or administrator already exists.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col justify-center items-center px-4 py-12">
      {/* Background radial gradient accent */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_80%_80%_at_50%_-20%,rgba(13,148,136,0.15),rgba(255,255,255,0))] pointer-events-none" />

      <div className="relative w-full max-w-md animate-fade-in-up">
        {/* Hospital Branding Header */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-teal-500/10 border border-teal-500/30 text-teal-400 mb-4 shadow-lg shadow-teal-500/10 pulse-glow transition-all duration-300">
            <Building2 className="w-7 h-7" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-white uppercase">SIMS Hospital</h1>
          <p className="text-xs font-semibold uppercase tracking-widest text-teal-400 mt-1">
            Ambulatory Care & Clinical Documentation System
          </p>
          <p className="text-xs text-slate-400 mt-1.5">
            Secure clinical workstation with live ambient AI transcription
          </p>
        </div>

        {/* Card Container */}
        <div className="bg-slate-900/90 backdrop-blur-xl border border-slate-800 rounded-3xl p-6 sm:p-8 shadow-2xl transition-all duration-300 hover:border-slate-700/80">
          {/* Animated Tab Selector with Sliding Pill */}
          <div className="relative p-1 bg-slate-950/80 rounded-2xl border border-slate-800/80 mb-6 flex">
            {/* Sliding background indicator pill */}
            <div
              className={`absolute top-1 bottom-1 w-[calc(50%-4px)] bg-teal-500 rounded-xl shadow-md transition-all duration-300 ease-out pointer-events-none ${
                activeTab === 'DOCTOR' ? 'left-1' : 'left-[calc(50%+2px)]'
              }`}
            />
            <button
              type="button"
              onClick={() => {
                setActiveTab('DOCTOR')
                setError(null)
              }}
              className={`relative z-10 flex-1 flex items-center justify-center gap-2 py-2 px-3 rounded-xl text-xs font-bold transition-colors duration-200 ${
                activeTab === 'DOCTOR'
                  ? 'text-slate-950 font-extrabold'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Stethoscope className="w-3.5 h-3.5" />
              Doctor Sign In
            </button>
            <button
              type="button"
              onClick={() => {
                setActiveTab('ADMIN')
                setError(null)
              }}
              className={`relative z-10 flex-1 flex items-center justify-center gap-2 py-2 px-3 rounded-xl text-xs font-bold transition-colors duration-200 ${
                activeTab === 'ADMIN'
                  ? 'text-slate-950 font-extrabold'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <ShieldCheck className="w-3.5 h-3.5" />
              Admin Portal
            </button>
          </div>

          {/* Feedback alerts */}
          {error && (
            <div className="mb-5 flex items-start gap-2.5 p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs animate-fade-in-down">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-rose-400" />
              <p className="leading-relaxed">{error}</p>
            </div>
          )}

          {successMessage && (
            <div className="mb-5 flex items-start gap-2.5 p-3 rounded-xl bg-teal-500/10 border border-teal-500/20 text-teal-300 text-xs animate-fade-in-down">
              <ShieldCheck className="w-4 h-4 shrink-0 mt-0.5 text-teal-400" />
              <p className="leading-relaxed">{successMessage}</p>
            </div>
          )}

          {/* DOCTOR TAB */}
          {activeTab === 'DOCTOR' && (
            <form onSubmit={handleDoctorLogin} className="space-y-4 animate-tab-slide">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">
                  Doctor ID or Registered Email
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-500">
                    <User className="w-4 h-4" />
                  </div>
                  <input
                    type="text"
                    value={doctorIdentifier}
                    onChange={(e) => setDoctorIdentifier(e.target.value)}
                    placeholder="e.g. DOC-101 or doctor@simshospital.com"
                    autoComplete="username"
                    required
                    className="w-full pl-10 pr-3.5 py-2.5 bg-slate-950/60 border border-slate-700/80 rounded-xl text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-teal-500 focus:ring-1 focus:ring-teal-500 transition-colors"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">Password</label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-500">
                    <Lock className="w-4 h-4" />
                  </div>
                  <input
                    type="password"
                    value={doctorPassword}
                    onChange={(e) => setDoctorPassword(e.target.value)}
                    placeholder="Enter assigned password"
                    autoComplete="current-password"
                    required
                    className="w-full pl-10 pr-3.5 py-2.5 bg-slate-950/60 border border-slate-700/80 rounded-xl text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-teal-500 focus:ring-1 focus:ring-teal-500 transition-colors"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full mt-2 flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl bg-teal-500 hover:bg-teal-400 text-slate-950 font-bold text-sm shadow-md shadow-teal-500/10 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Authenticating Doctor...
                  </>
                ) : (
                  <>
                    Access Clinical Workstation
                    <ChevronRight className="w-4 h-4" />
                  </>
                )}
              </button>

              <div className="pt-3 border-t border-slate-800 text-center">
                <div className="flex items-center gap-2 p-2.5 rounded-xl bg-slate-950/50 border border-slate-800 text-left">
                  <KeyRound className="w-4 h-4 text-teal-400 shrink-0 mt-0.5" />
                  <p className="text-2xs text-slate-400 leading-relaxed">
                    Doctor accounts are provisioned exclusively by Hospital Administration. If you do not have an assigned Doctor ID, please contact the Medical Administration desk.
                  </p>
                </div>
              </div>
            </form>
          )}

          {/* ADMIN TAB */}
          {activeTab === 'ADMIN' && (
            <div className="animate-tab-slide">
              {!isAdminSetup ? (
                <form onSubmit={handleAdminLogin} className="space-y-4 animate-fade-in-up">
                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1.5">
                      Administrator Email
                    </label>
                    <div className="relative">
                      <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-500">
                        <Mail className="w-4 h-4" />
                      </div>
                      <input
                        type="email"
                        value={adminEmail}
                        onChange={(e) => setAdminEmail(e.target.value)}
                        placeholder="admin@simshospital.com"
                        autoComplete="email"
                        required
                        className="w-full pl-10 pr-3.5 py-2.5 bg-slate-950/60 border border-slate-700/80 rounded-xl text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-teal-500 focus:ring-1 focus:ring-teal-500 transition-colors"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1.5">Password</label>
                    <div className="relative">
                      <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-500">
                        <Lock className="w-4 h-4" />
                      </div>
                      <input
                        type="password"
                        value={adminPassword}
                        onChange={(e) => setAdminPassword(e.target.value)}
                        placeholder="Enter administrator password"
                        autoComplete="current-password"
                        required
                        className="w-full pl-10 pr-3.5 py-2.5 bg-slate-950/60 border border-slate-700/80 rounded-xl text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-teal-500 focus:ring-1 focus:ring-teal-500 transition-colors"
                      />
                    </div>
                  </div>

                  <button
                    type="submit"
                    disabled={loading}
                    className="w-full mt-2 flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl bg-teal-500 hover:bg-teal-400 text-slate-950 font-bold text-sm shadow-md shadow-teal-500/10 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {loading ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        Authenticating Administrator...
                      </>
                    ) : (
                      <>
                        Sign In as Administrator
                        <ChevronRight className="w-4 h-4" />
                      </>
                    )}
                  </button>

                  <div className="pt-3 border-t border-slate-800 text-center">
                    <button
                      type="button"
                      onClick={() => {
                        setIsAdminSetup(true)
                        setError(null)
                      }}
                      className="text-xs text-teal-400 hover:text-teal-300 font-medium underline underline-offset-4"
                    >
                      First-time system setup? Register initial Administrator
                    </button>
                  </div>
                </form>
              ) : (
                <form onSubmit={handleAdminSetup} className="space-y-3.5">
                  <div className="p-2.5 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-300 text-xs flex items-start gap-2">
                    <ShieldAlert className="w-4 h-4 shrink-0 mt-0.5 text-amber-400" />
                    <p className="leading-snug">
                      Initial setup is allowed only once. Once configured, public registration will be locked.
                    </p>
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">Full Name</label>
                    <input
                      type="text"
                      value={adminFullName}
                      onChange={(e) => setAdminFullName(e.target.value)}
                      placeholder="e.g. Dr. Administrator"
                      required
                      className="w-full px-3 py-2 bg-slate-950/60 border border-slate-700/80 rounded-xl text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-teal-500 focus:ring-1 focus:ring-teal-500"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">Administrator Email</label>
                    <input
                      type="email"
                      value={adminEmail}
                      onChange={(e) => setAdminEmail(e.target.value)}
                      placeholder="admin@simshospital.com"
                      required
                      className="w-full px-3 py-2 bg-slate-950/60 border border-slate-700/80 rounded-xl text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-teal-500 focus:ring-1 focus:ring-teal-500"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">Password</label>
                    <input
                      type="password"
                      value={adminPassword}
                      onChange={(e) => setAdminPassword(e.target.value)}
                      placeholder="Minimum 8 characters"
                      required
                      className="w-full px-3 py-2 bg-slate-950/60 border border-slate-700/80 rounded-xl text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-teal-500 focus:ring-1 focus:ring-teal-500"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">Confirm Password</label>
                    <input
                      type="password"
                      value={adminConfirmPassword}
                      onChange={(e) => setAdminConfirmPassword(e.target.value)}
                      placeholder="Re-enter password"
                      required
                      className="w-full px-3 py-2 bg-slate-950/60 border border-slate-700/80 rounded-xl text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-teal-500 focus:ring-1 focus:ring-teal-500"
                    />
                  </div>

                  <button
                    type="submit"
                    disabled={loading}
                    className="w-full mt-2 flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl bg-teal-500 hover:bg-teal-400 text-slate-950 font-bold text-sm shadow-md shadow-teal-500/10 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {loading ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        Setting Up Administrator...
                      </>
                    ) : (
                      'Complete Initial Setup'
                    )}
                  </button>

                  <div className="pt-2 text-center">
                    <button
                      type="button"
                      onClick={() => {
                        setIsAdminSetup(false)
                        setError(null)
                      }}
                      className="text-xs text-slate-400 hover:text-slate-200"
                    >
                      Back to Administrator Sign In
                    </button>
                  </div>
                </form>
              )}
            </div>
          )}
        </div>

        {/* Footer info */}
        <div className="text-center mt-6 text-2xs text-slate-500">
          SIMS Hospital Clinical Informatics &middot; Encrypted &amp; Audited Access
        </div>
      </div>
    </div>
  )
}
