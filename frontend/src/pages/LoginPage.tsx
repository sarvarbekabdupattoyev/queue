import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { homeFor, useAuth } from '../auth/AuthContext'
import { AuthShell } from '../components/AuthShell'
import { ActionForm, Field } from '../components/ui'
import { useLang } from '../i18n'

export default function LoginPage() {
  const { user, login } = useAuth()
  const { t } = useLang()
  const navigate = useNavigate()
  const [phone, setPhone] = useState('+998')
  const [password, setPassword] = useState('')

  if (user) return <Navigate to={homeFor(user.role)} replace />

  return (
    <AuthShell>
      <h1>{t.auth.loginTitle}</h1>
      <p className="sub">{t.auth.loginSub}</p>
      <ActionForm
        onSubmit={async () => {
          const logged = await login(phone, password)
          navigate(homeFor(logged.role), { replace: true })
        }}
      >
        {(busy, error) => (
          <>
            <Field label={t.auth.phone}>
              <input
                className="input"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="+998 90 123 45 67"
                autoComplete="tel"
                required
              />
            </Field>
            <Field label={t.auth.password}>
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
              {busy ? t.auth.submitLoginBusy : t.auth.submitLogin}
            </button>
            <p className="auth-foot">
              {t.auth.noAccount} <Link to="/register">{t.auth.registerLink}</Link>
            </p>
          </>
        )}
      </ActionForm>
    </AuthShell>
  )
}
