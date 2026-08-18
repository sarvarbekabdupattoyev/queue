import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { homeFor, useAuth } from '../auth/AuthContext'
import { AuthShell } from '../components/AuthShell'
import { ActionForm, Field } from '../components/ui'
import { useLang } from '../i18n'

export default function RegisterPage() {
  const { user, registerOwner } = useAuth()
  const { t } = useLang()
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
    <AuthShell>
      <h1>{t.auth.registerTitle}</h1>
      <p className="sub">{t.auth.registerSub}</p>
      <ActionForm
        onSubmit={async () => {
          await registerOwner(form)
          navigate('/onboarding', { replace: true })
        }}
      >
        {(busy, error) => (
          <>
            <div className="grid-2" style={{ gap: 12 }}>
              <Field label={t.auth.firstName}>
                <input
                  className="input"
                  value={form.first_name}
                  onChange={set('first_name')}
                  required
                  minLength={2}
                  autoComplete="given-name"
                />
              </Field>
              <Field label={t.auth.lastName}>
                <input
                  className="input"
                  value={form.last_name}
                  onChange={set('last_name')}
                  autoComplete="family-name"
                />
              </Field>
            </div>
            <Field label={t.auth.phone}>
              <input
                className="input"
                value={form.phone}
                onChange={set('phone')}
                placeholder="+998 90 123 45 67"
                autoComplete="tel"
                required
              />
            </Field>
            <Field label={t.auth.passwordNew}>
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
              {busy ? t.auth.submitRegisterBusy : t.auth.submitRegister}
            </button>
            <p className="auth-foot">
              {t.auth.haveAccount} <Link to="/login">{t.auth.loginLink}</Link>
            </p>
          </>
        )}
      </ActionForm>
    </AuthShell>
  )
}
