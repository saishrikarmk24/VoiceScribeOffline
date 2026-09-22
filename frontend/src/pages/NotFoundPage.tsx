import { Link } from 'react-router-dom'
import { Compass } from 'lucide-react'

export function NotFoundPage() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
      <Compass className="h-8 w-8 text-navy-300" aria-hidden />
      <div>
        <p className="text-sm font-semibold text-navy-900">Page not found</p>
        <p className="text-xs text-navy-500">The route you requested does not exist in MedScribe Live.</p>
      </div>
      <Link to="/" className="btn-primary">
        Back to dashboard
      </Link>
    </div>
  )
}
