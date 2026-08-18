import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { homeFor, useAuth } from '../auth/AuthContext'
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
      <div className="auth-card">
        <div className="brand">
          <div className="brand-mark">
            NAV<span>BAT</span>
          </div>
          <div className="brand-sub">Hisob yaratish</div>
        </div>
        <ActionForm
          onSubmit={async () => {
            await registerOwner(form)
            navigate('/onboarding', { replace: true })
          }}
        >
          {(busy, error) => (
            <>
              <Field label="Ism">
                <input className="input" value={form.first_name} onChange={set('first_name')} required minLength={2} />
              </Field>
              <Field label="Familiya">
                <input className="input" value={form.last_name} onChange={set('last_name')} />
              </Field>
              <Field label="Telefon raqam">
                <input className="input" value={form.phone} onChange={set('phone')} placeholder="+998 90 123 45 67" required />
              </Field>
              <Field label="Parol (kamida 6 belgi)">
                <input className="input" type="password" value={form.password} onChange={set('password')} required minLength={6} />
              </Field>
              {error && <div className="error-text">{error}</div>}
              <button className="btn full big" style={{ marginTop: 10 }} disabled={busy}>
                {busy ? 'Yaratilmoqda…' : 'Hisob yaratish'}
              </button>
              <p className="hint" style={{ textAlign: 'center', marginTop: 16 }}>
                Hisobingiz bormi? <Link to="/login">Kirish</Link>
              </p>
            </>
          )}
        </ActionForm>
      </div>
    </div>
  )
}
