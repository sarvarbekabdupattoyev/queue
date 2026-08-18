import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { homeFor, useAuth } from '../auth/AuthContext'
import { ThemeToggle } from '../components/ThemeToggle'
import { Wordmark } from '../components/icons'
import { ActionForm, Field } from '../components/ui'

export default function RegisterPage() {
  const { user, registerOwner } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState({
    first_name: '',
    last_name: '',
    phone: '+998',
    password: '',
  })
  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }))

  if (user) return <Navigate to={homeFor(user.role)} replace />

  return (
    <div className="auth-shell">
      <div className="auth-corner">
        <ThemeToggle />
      </div>
      <div className="auth-card">
        <div className="brand">
          <Wordmark size={34} stacked />
        </div>
        <p className="brand-sub">Hisob yarating — 1 daqiqa kifoya</p>
        <ActionForm
          onSubmit={async () => {
            await registerOwner(form)
            navigate('/onboarding', { replace: true })
          }}
        >
          {(busy, error) => (
            <>
              <div className="grid-2" style={{ gap: 12 }}>
                <Field label="Ism">
                  <input
                    className="input"
                    value={form.first_name}
                    onChange={set('first_name')}
                    required
                    minLength={2}
                    autoComplete="given-name"
                  />
                </Field>
                <Field label="Familiya">
                  <input
                    className="input"
                    value={form.last_name}
                    onChange={set('last_name')}
                    autoComplete="family-name"
                  />
                </Field>
              </div>
              <Field label="Telefon raqam">
                <input
                  className="input"
                  value={form.phone}
                  onChange={set('phone')}
                  placeholder="+998 90 123 45 67"
                  autoComplete="tel"
                  required
                />
              </Field>
              <Field label="Parol (kamida 6 belgi)">
                <input
                  className="input"
                  type="password"
                  value={form.password}
                  onChange={set('password')}
                  autoComplete="new-password"
                  required
                  minLength={6}
                />
              </Field>
              {error && <div className="error-text">{error}</div>}
              <button className="btn full big" style={{ marginTop: 12 }} disabled={busy}>
                {busy ? 'Yaratilmoqda…' : 'Hisob yaratish'}
              </button>
              <p className="auth-foot">
                Hisobingiz bormi? <Link to="/login">Kirish</Link>
              </p>
            </>
          )}
        </ActionForm>
      </div>
    </div>
  )
}
