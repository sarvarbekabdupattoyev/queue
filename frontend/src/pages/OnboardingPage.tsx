import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import type { Company } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { ActionForm, Field } from '../components/ui'

export default function OnboardingPage() {
  const { user, refresh } = useAuth()
  const navigate = useNavigate()
  const [name, setName] = useState('')

  if (user && user.company_id !== null) return <Navigate to="/dashboard" replace />

  return (
    <div className="auth-shell">
      <div className="auth-card">
        <div className="brand">
          <div className="brand-mark">
            NAV<span>BAT</span>
          </div>
          <div className="brand-sub">Kompaniyangizni yarating</div>
        </div>
        <p className="hint" style={{ marginBottom: 16 }}>
          Xush kelibsiz, {user?.first_name}! Ishni boshlash uchun kompaniyangiz nomini kiriting.
          Keyin xodimlar, stollar va sotuv tadbirlarini qo‘shasiz.
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
