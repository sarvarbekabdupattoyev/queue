import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { homeFor, useAuth } from '../auth/AuthContext'
import { ThemeToggle } from '../components/ThemeToggle'
import { Wordmark } from '../components/icons'
import { ActionForm, Field } from '../components/ui'

export default function LoginPage() {
  const { user, login } = useAuth()
  const navigate = useNavigate()
  const [phone, setPhone] = useState('+998')
  const [password, setPassword] = useState('')

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
        <p className="brand-sub">Sotuv kunlari uchun onlayn navbat tizimi</p>
        <ActionForm
          onSubmit={async () => {
            const logged = await login(phone, password)
            navigate(homeFor(logged.role), { replace: true })
          }}
        >
          {(busy, error) => (
            <>
              <Field label="Telefon raqam">
                <input
                  className="input"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="+998 90 123 45 67"
                  autoComplete="tel"
                  required
                />
              </Field>
              <Field label="Parol">
                <input
                  className="input"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  required
                />
              </Field>
              {error && <div className="error-text">{error}</div>}
              <button className="btn full big" style={{ marginTop: 12 }} disabled={busy}>
                {busy ? 'Kirilmoqda…' : 'Kirish'}
              </button>
              <p className="auth-foot">
                Kompaniyangiz yo‘qmi? <Link to="/register">Ro‘yxatdan o‘ting</Link>
              </p>
            </>
          )}
        </ActionForm>
      </div>
    </div>
  )
}
