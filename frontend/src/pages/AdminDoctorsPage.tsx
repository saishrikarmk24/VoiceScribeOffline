import React, { useEffect, useState } from 'react'
import {
  UserPlus,
  Search,
  ShieldCheck,
  Stethoscope,
  KeyRound,
  CheckCircle2,
  XCircle,
  AlertCircle,
  RefreshCw,
  X,
  Loader2,
} from 'lucide-react'
import { api } from '@/services/api'
import { MedicalPulseLoader } from '@/components/ui/MedicalAnimations'
import type { AuthUser, DoctorCreatePayload } from '@/types'

const DEPARTMENTS = [
  'General Medicine',
  'Ambulatory Care',
  'Cardiology',
  'Pediatrics',
  'Neurology',
  'Orthopedics',
  'Emergency Medicine',
  'Dermatology',
  'Pulmonology',
  'Obstetrics & Gynecology',
]

export function AdminDoctorsPage() {
  const [doctors, setDoctors] = useState<AuthUser[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')

  // Modal State
  const [isAddModalOpen, setIsAddModalOpen] = useState(false)
  const [isResetModalOpen, setIsResetModalOpen] = useState(false)
  const [selectedDoctor, setSelectedDoctor] = useState<AuthUser | null>(null)
  const [resetNewPassword, setResetNewPassword] = useState('')

  // Form State for Provisioning
  const [formData, setFormData] = useState<DoctorCreatePayload>({
    doctor_id: '',
    full_name: '',
    email: '',
    department: 'General Medicine',
    password: '',
  })
  const [submitting, setSubmitting] = useState(false)

  const loadDoctors = async () => {
    setLoading(true)
    try {
      const data = await api.listDoctors()
      setDoctors(data)
      setError(null)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to retrieve doctors list.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadDoctors()
  }, [])

  const handleCreateDoctor = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    setSuccess(null)

    try {
      const created = await api.createDoctor({
        doctor_id: formData.doctor_id.trim().toUpperCase(),
        full_name: formData.full_name.trim(),
        email: formData.email.trim().toLowerCase(),
        department: formData.department.trim(),
        password: formData.password,
      })
      setSuccess(`Doctor ${created.doctor_id} (${created.full_name}) provisioned successfully.`)
      setIsAddModalOpen(false)
      setFormData({
        doctor_id: '',
        full_name: '',
        email: '',
        department: 'General Medicine',
        password: '',
      })
      await loadDoctors()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to provision doctor.')
    } finally {
      setSubmitting(false)
    }
  }

  const handleToggleStatus = async (doctor: AuthUser) => {
    try {
      const updated = await api.updateDoctorStatus(doctor.id, !doctor.is_active)
      setDoctors((prev) => prev.map((d) => (d.id === updated.id ? updated : d)))
      setSuccess(`Doctor ${doctor.doctor_id} status updated to ${updated.is_active ? 'Active' : 'Suspended'}.`)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to change doctor status.')
    }
  }

  const handleResetPassword = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedDoctor || !resetNewPassword) return

    setSubmitting(true)
    setError(null)
    setSuccess(null)

    try {
      await api.resetDoctorPassword(selectedDoctor.id, resetNewPassword)
      setSuccess(`Password for Doctor ${selectedDoctor.doctor_id || selectedDoctor.full_name} has been updated.`)
      setIsResetModalOpen(false)
      setSelectedDoctor(null)
      setResetNewPassword('')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to reset password.')
    } finally {
      setSubmitting(false)
    }
  }

  const generateRandomPassword = () => {
    const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789!@#$'
    let pass = ''
    for (let i = 0; i < 10; i++) {
      pass += chars.charAt(Math.floor(Math.random() * chars.length))
    }
    setFormData((prev) => ({ ...prev, password: pass }))
  }

  const filteredDoctors = doctors.filter((doc) => {
    const q = searchQuery.toLowerCase()
    return (
      (doc.doctor_id && doc.doctor_id.toLowerCase().includes(q)) ||
      doc.full_name.toLowerCase().includes(q) ||
      doc.email.toLowerCase().includes(q) ||
      (doc.department && doc.department.toLowerCase().includes(q))
    )
  })

  return (
    <div className="h-full flex flex-col p-6 overflow-y-auto bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 transition-colors duration-200">
      {/* Header section */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-200 dark:border-slate-800 pb-5 mb-6">
        <div>
          <div className="flex items-center gap-2 text-teal-700 dark:text-teal-400 font-semibold text-xs tracking-wider uppercase">
            <ShieldCheck className="w-4 h-4" />
            Hospital Administration Portal
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100 mt-1">Doctor ID Provisioning</h1>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            Assign unique Doctor IDs, departments, and credentials. Doctors access the workstation using their assigned ID.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={loadDoctors}
            disabled={loading}
            className="p-2.5 rounded-xl border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
            title="Refresh Doctor List"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
          <button
            type="button"
            onClick={() => {
              setIsAddModalOpen(true)
              setError(null)
              setSuccess(null)
            }}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-teal-600 hover:bg-teal-700 text-white font-semibold text-xs shadow-sm transition-all interactive-card"
          >
            <UserPlus className="w-4 h-4" />
            Provision New Doctor ID
          </button>
        </div>
      </div>

      {/* Alerts */}
      {error && (
        <div className="mb-4 flex items-start gap-2.5 p-3 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900/60 text-rose-800 dark:text-rose-300 text-xs">
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-rose-600" />
          <p>{error}</p>
        </div>
      )}

      {success && (
        <div className="mb-4 flex items-start gap-2.5 p-3 rounded-xl bg-teal-50 dark:bg-teal-950/40 border border-teal-200 dark:border-teal-900/60 text-teal-800 dark:text-teal-300 text-xs">
          <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5 text-teal-600" />
          <p>{success}</p>
        </div>
      )}

      {/* Filter and stats */}
      <div className="flex items-center justify-between gap-4 mb-4">
        <div className="relative flex-1 max-w-sm">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder="Search by Doctor ID, name, email, or department..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-3 py-2 text-xs bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl focus:outline-none focus:bg-white dark:focus:bg-slate-900 focus:border-teal-500 focus:ring-1 focus:ring-teal-500 text-slate-900 dark:text-slate-100"
          />
        </div>
        <div className="text-xs text-slate-500 dark:text-slate-400 font-medium">
          Total Doctors: <span className="font-semibold text-slate-800 dark:text-slate-200">{doctors.length}</span>
        </div>
      </div>

      {/* Doctors Table */}
      <div className="flex-1 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl overflow-hidden shadow-xs flex flex-col">
        {loading && doctors.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center p-12">
            <MedicalPulseLoader
              label="Synchronizing Doctor Directory"
              sublabel="Accessing hospital credential registries and active sessions"
              size="md"
            />
          </div>
        ) : filteredDoctors.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center p-12 text-center text-slate-400 dark:text-slate-500">
            <Stethoscope className="w-10 h-10 text-slate-300 dark:text-slate-600 mb-3" />
            <p className="text-sm font-semibold text-slate-700 dark:text-slate-300">No doctors found</p>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 max-w-sm">
              {searchQuery
                ? 'No provisioned doctor matches your search query.'
                : 'Click "Provision New Doctor ID" to assign credentials to doctors.'}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-800 bg-slate-50/80 dark:bg-slate-950/70 text-slate-600 dark:text-slate-400 uppercase tracking-wider font-semibold text-2xs">
                  <th className="py-3 px-4">Doctor ID</th>
                  <th className="py-3 px-4">Doctor Name</th>
                  <th className="py-3 px-4">Department</th>
                  <th className="py-3 px-4">Email</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4">Last Login</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {filteredDoctors.map((doc) => (
                  <tr key={doc.id} className="hover:bg-slate-50/60 dark:hover:bg-slate-800/40 transition-colors">
                    <td className="py-3 px-4 font-bold text-teal-700 dark:text-teal-400">
                      <span className="inline-flex items-center px-2 py-0.5 rounded-md bg-teal-50 dark:bg-teal-950/60 border border-teal-200 dark:border-teal-800 text-teal-800 dark:text-teal-300 font-mono">
                        {doc.doctor_id || 'DOC-UNASSIGNED'}
                      </span>
                    </td>
                    <td className="py-3 px-4 font-semibold text-slate-900 dark:text-slate-100">{doc.full_name}</td>
                    <td className="py-3 px-4 text-slate-600 dark:text-slate-300">{doc.department || 'General Medicine'}</td>
                    <td className="py-3 px-4 text-slate-500 dark:text-slate-400 font-mono text-2xs">{doc.email}</td>
                    <td className="py-3 px-4">
                      {doc.is_active ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-2xs font-semibold bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800">
                          <CheckCircle2 className="w-3 h-3" /> Active
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-2xs font-semibold bg-rose-50 dark:bg-rose-950/60 text-rose-700 dark:text-rose-400 border border-rose-200 dark:border-rose-800">
                          <XCircle className="w-3 h-3" /> Suspended
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-slate-400 dark:text-slate-500 text-2xs">
                      {doc.last_login_at
                        ? new Date(doc.last_login_at).toLocaleString(undefined, {
                            dateStyle: 'medium',
                            timeStyle: 'short',
                          })
                        : 'Never'}
                    </td>
                    <td className="py-3 px-4 text-right space-x-2">
                      <button
                        type="button"
                        onClick={() => {
                          setSelectedDoctor(doc)
                          setResetNewPassword('')
                          setIsResetModalOpen(true)
                        }}
                        className="px-2.5 py-1 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors font-medium text-2xs"
                      >
                        Reset Password
                      </button>
                      <button
                        type="button"
                        onClick={() => handleToggleStatus(doc)}
                        className={`px-2.5 py-1 rounded-lg font-medium text-2xs transition-colors border ${
                          doc.is_active
                            ? 'border-amber-200 dark:border-amber-800 text-amber-700 dark:text-amber-400 hover:bg-amber-50 dark:hover:bg-amber-950/50'
                            : 'border-emerald-200 dark:border-emerald-800 text-emerald-700 dark:text-emerald-400 hover:bg-emerald-50 dark:hover:bg-emerald-950/50'
                        }`}
                      >
                        {doc.is_active ? 'Suspend' : 'Activate'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* PROVISION NEW DOCTOR MODAL */}
      {isAddModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-xs">
          <div className="bg-white dark:bg-slate-900 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-2xl w-full max-w-lg overflow-hidden animate-scale-spring text-slate-900 dark:text-slate-100">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/50">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-xl bg-teal-500/10 text-teal-600 dark:text-teal-400 flex items-center justify-center">
                  <UserPlus className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">Provision Doctor ID</h3>
                  <p className="text-2xs text-slate-500 dark:text-slate-400">Create new doctor login credentials</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setIsAddModalOpen(false)}
                className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 p-1 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleCreateDoctor} className="p-6 space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                    Doctor ID <span className="text-rose-500">*</span>
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. DOC-101"
                    value={formData.doctor_id}
                    onChange={(e) => setFormData({ ...formData, doctor_id: e.target.value.toUpperCase() })}
                    className="w-full px-3 py-2 text-xs uppercase font-mono font-bold bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl focus:outline-none focus:bg-white dark:focus:bg-slate-900 focus:border-teal-500 focus:ring-1 focus:ring-teal-500 text-slate-900 dark:text-slate-100"
                  />
                  <p className="text-2xs text-slate-400 dark:text-slate-500 mt-1">Unique doctor badge identifier</p>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                    Department <span className="text-rose-500">*</span>
                  </label>
                  <select
                    value={formData.department}
                    onChange={(e) => setFormData({ ...formData, department: e.target.value })}
                    className="w-full px-3 py-2 text-xs bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl focus:outline-none focus:bg-white dark:focus:bg-slate-900 focus:border-teal-500 focus:ring-1 focus:ring-teal-500 text-slate-900 dark:text-slate-100"
                  >
                    {DEPARTMENTS.map((dept) => (
                      <option key={dept} value={dept}>
                        {dept}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Doctor Full Name <span className="text-rose-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Dr. Arvind Swaminathan, MD"
                  value={formData.full_name}
                  onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
                  className="w-full px-3 py-2 text-xs bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl focus:outline-none focus:bg-white dark:focus:bg-slate-900 focus:border-teal-500 focus:ring-1 focus:ring-teal-500 text-slate-900 dark:text-slate-100"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Official Email <span className="text-rose-500">*</span>
                </label>
                <input
                  type="email"
                  required
                  placeholder="doctor@simshospital.com"
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  className="w-full px-3 py-2 text-xs bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl focus:outline-none focus:bg-white dark:focus:bg-slate-900 focus:border-teal-500 focus:ring-1 focus:ring-teal-500 text-slate-900 dark:text-slate-100"
                />
              </div>

              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300">
                    Initial Password <span className="text-rose-500">*</span>
                  </label>
                  <button
                    type="button"
                    onClick={generateRandomPassword}
                    className="text-2xs text-teal-600 dark:text-teal-400 hover:text-teal-500 font-semibold"
                  >
                    Generate Secure
                  </button>
                </div>
                <input
                  type="text"
                  required
                  placeholder="Minimum 6 characters"
                  value={formData.password}
                  onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                  className="w-full px-3 py-2 text-xs font-mono bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl focus:outline-none focus:bg-white dark:focus:bg-slate-900 focus:border-teal-500 focus:ring-1 focus:ring-teal-500 text-slate-900 dark:text-slate-100"
                />
              </div>

              <div className="pt-3 border-t border-slate-100 dark:border-slate-800 flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setIsAddModalOpen(false)}
                  className="px-4 py-2 text-xs font-medium text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-xl transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="px-4 py-2 text-xs font-semibold text-white bg-teal-600 hover:bg-teal-700 rounded-xl shadow-xs transition-all disabled:opacity-50 flex items-center gap-1.5 interactive-card"
                >
                  {submitting ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      Provisioning...
                    </>
                  ) : (
                    'Provision Doctor ID'
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* RESET PASSWORD MODAL */}
      {isResetModalOpen && selectedDoctor && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-xs">
          <div className="bg-white dark:bg-slate-900 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-2xl w-full max-w-sm overflow-hidden animate-scale-spring text-slate-900 dark:text-slate-100">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/50">
              <div className="flex items-center gap-2">
                <KeyRound className="w-4 h-4 text-teal-600 dark:text-teal-400" />
                <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">Reset Password</h3>
              </div>
              <button
                type="button"
                onClick={() => setIsResetModalOpen(false)}
                className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 p-1 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleResetPassword} className="p-6 space-y-4">
              <p className="text-xs text-slate-600 dark:text-slate-400">
                Reset password for <span className="font-semibold text-slate-900 dark:text-slate-100">{selectedDoctor.full_name}</span> (
                <span className="font-mono text-teal-700 dark:text-teal-400">{selectedDoctor.doctor_id || selectedDoctor.email}</span>):
              </p>

              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">New Password</label>
                <input
                  type="text"
                  required
                  placeholder="Enter new password (min 6 characters)"
                  value={resetNewPassword}
                  onChange={(e) => setResetNewPassword(e.target.value)}
                  className="w-full px-3 py-2 text-xs font-mono bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl focus:outline-none focus:bg-white dark:focus:bg-slate-900 focus:border-teal-500 focus:ring-1 focus:ring-teal-500 text-slate-900 dark:text-slate-100"
                />
              </div>

              <div className="pt-2 flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setIsResetModalOpen(false)}
                  className="px-3.5 py-1.5 text-xs font-medium text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-xl transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="px-4 py-1.5 text-xs font-semibold text-white bg-teal-600 hover:bg-teal-700 rounded-xl shadow-xs transition-all disabled:opacity-50 flex items-center gap-1.5 interactive-card"
                >
                  {submitting ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      Updating...
                    </>
                  ) : (
                    'Update Password'
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
