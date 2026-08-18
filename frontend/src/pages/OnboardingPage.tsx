import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import type { Company } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { ThemeToggle } from '../components/ThemeToggle'
import { Wordmark } from '../components/icons'
import { ActionForm, Field } from '../components/ui'

export default function OnboardingPage() {
  const { user, refresh } = useAuth()
  const navigate = useNavigate()
  const [name, setName] = useState('')

  if (user && user.company_id !== null) return <Navigate to="/dashboard" replace />

  return (
    <div className="auth-shell">
      <span className="blobs" aria-hidden="true">
        <i />
        <i />
        <i />
      </span>
      <div className="auth-corner">
        <ThemeToggle />
      </div>
      <div className="auth-card">
        <div className="brand">
          <Wordmark size={34} stacked />
        </div>
        <p className="brand-sub">
          Xush kelibsiz, {user?.first_name}! Boshlash uchun kompaniyangiz nomini kiriting —
          keyin xodimlar, stollar va sotuv tadbirlarini qo‘shasiz.
        </p>
        <ActionForm
          onSubmit={async () => {
            await api<Company>('/company', { body: { name } })
            await refresh()
            navigate('/dashboard', { replace: true })
          }}
        >
          {(busy, error) => (
            <>
              <Field label="Kompaniya nomi">
                <input
                  className="input"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Masalan: Bahor City"
                  required
                  minLength={2}
                  autoFocus
                />
              </Field>
              {error && <div className="error-text">{error}</div>}
              <button className="btn full big" disabled={busy}>
                {busy ? 'Yaratilmoqda…' : 'Kompaniya yaratish'}
              </button>
            </>
          )}
        </ActionForm>
      </div>
    </div>
  )
}
