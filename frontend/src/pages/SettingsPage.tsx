import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { Company } from '../api/types'
import { ActionForm, Field, Spinner, useToast } from '../components/ui'
import { useCompany } from '../components/DashboardLayout'
import { prettyPhone } from '../lib/format'

export default function SettingsPage() {
  const { data: company, isLoading } = useCompany()
  const queryClient = useQueryClient()
  const toast = useToast()
  const [name, setName] = useState('')
  const [botToken, setBotToken] = useState('')
  const [phoneForm, setPhoneForm] = useState({ phone: '+998', label: '' })
  const [locationForm, setLocationForm] = useState({ name: '', address: '', map_url: '' })

  useEffect(() => {
    if (company) setName(company.name)
  }, [company])

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['company'] })

  const uploadLogo = useMutation({
    mutationFn: (file: File) => {
      const formData = new FormData()
      formData.append('file', file)
      return api<Company>('/company/logo', { formData })
    },
    onSuccess: () => {
      invalidate()
      toast('Logo yangilandi')
    },
    onError: (e: Error) => toast(e.message, true),
  })
  const deletePhone = useMutation({
    mutationFn: (id: number) => api(`/company/phones/${id}`, { method: 'DELETE' }),
    onSuccess: invalidate,
  })
  const deleteLocation = useMutation({
    mutationFn: (id: number) => api(`/company/locations/${id}`, { method: 'DELETE' }),
    onSuccess: invalidate,
  })

  if (isLoading || !company) return <Spinner />

  return (
    <>
      <div className="page-actions">
        <span className="hint">
          Kompaniya ma’lumotlari, aloqa raqamlari, manzillar va Telegram bot
        </span>
      </div>

      <div className="grid-2">
        <div className="card">
          <div className="card-title">Kompaniya</div>
          <ActionForm
            onSubmit={async () => {
              await api<Company>('/company', { method: 'PATCH', body: { name } })
              invalidate()
              toast('Saqlandi')
            }}
          >
            {(busy, error) => (
              <>
                <Field label="Kompaniya nomi">
                  <input className="input" value={name} onChange={(e) => setName(e.target.value)} required minLength={2} />
                </Field>
                {error && <div className="error-text">{error}</div>}
                <button className="btn" disabled={busy}>
                  Saqlash
                </button>
              </>
            )}
          </ActionForm>

          <div className="card-title" style={{ marginTop: 20 }}>
            Logo
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            {company.logo_url ? (
              <img src={company.logo_url} alt="Logo" style={{ height: 56, borderRadius: 10, background: '#fff', padding: 4 }} />
            ) : (
              <span className="muted">Logo yuklanmagan</span>
            )}
            <label className="btn ghost sm" style={{ cursor: 'pointer' }}>
              Logo yuklash
              <input
                type="file"
                accept="image/png,image/jpeg,image/webp,image/svg+xml"
                style={{ display: 'none' }}
                onChange={(e) => {
                  const file = e.target.files?.[0]
                  if (file) uploadLogo.mutate(file)
                  e.target.value = ''
                }}
              />
            </label>
          </div>
          <p className="hint" style={{ marginTop: 8 }}>
            PNG/JPEG/WebP/SVG, 2 MB gacha. Ofis ekranida ko‘rinadi.
          </p>
        </div>

        <div className="card">
          <div className="card-title">Telegram bot</div>
          {company.has_bot_token ? (
            <p style={{ marginBottom: 10 }}>
              Bot ulangan:{' '}
              {company.telegram_bot_username ? (
                <a href={`https://t.me/${company.telegram_bot_username}`} target="_blank" rel="noreferrer">
                  @{company.telegram_bot_username}
                </a>
              ) : (
                <span className="badge amber">token saqlangan, bot hozircha ishga tushmagan</span>
              )}
            </p>
          ) : (
            <p className="hint" style={{ marginBottom: 10 }}>
              Mijozlar ro‘yxatdan o‘tishi uchun bot kerak: Telegramda <b>@BotFather</b> ga{' '}
              <code>/newbot</code> yozing va olingan tokenni shu yerga qo‘ying.
            </p>
          )}
          <ActionForm
            onSubmit={async () => {
              await api<Company>('/company', { method: 'PATCH', body: { telegram_bot_token: botToken } })
              setBotToken('')
              invalidate()
              toast(botToken ? 'Bot token saqlandi' : 'Bot o‘chirildi')
            }}
          >
            {(busy, error) => (
              <>
                <Field label={company.has_bot_token ? 'Yangi token (bo‘sh yuborsangiz bot o‘chadi)' : 'Bot token'}>
                  <input
                    className="input"
                    value={botToken}
                    onChange={(e) => setBotToken(e.target.value)}
                    placeholder="123456789:AAH..."
                  />
                </Field>
                {error && <div className="error-text">{error}</div>}
                <button className="btn" disabled={busy}>
                  {busy ? 'Tekshirilmoqda…' : 'Saqlash'}
                </button>
              </>
            )}
          </ActionForm>
        </div>

        <div className="card">
          <div className="card-title">Aloqa raqamlari</div>
          {company.phones.length === 0 && <div className="empty">Raqam qo‘shilmagan</div>}
          {company.phones.map((phone) => (
            <div className="list-row" key={phone.id}>
              <span>
                {prettyPhone(phone.phone)} {phone.label && <span className="muted">· {phone.label}</span>}
              </span>
              <button className="btn ghost sm" onClick={() => deletePhone.mutate(phone.id)}>
                O‘chirish
              </button>
            </div>
          ))}
          <ActionForm
            onSubmit={async () => {
              await api('/company/phones', { body: phoneForm })
              setPhoneForm({ phone: '+998', label: '' })
              invalidate()
            }}
          >
            {(busy, error) => (
              <div style={{ marginTop: 12 }}>
                <div style={{ display: 'flex', gap: 8 }}>
                  <input
                    className="input"
                    value={phoneForm.phone}
                    onChange={(e) => setPhoneForm((f) => ({ ...f, phone: e.target.value }))}
                    placeholder="+998 71 200 50 50"
                    required
                  />
                  <input
                    className="input"
                    value={phoneForm.label}
                    onChange={(e) => setPhoneForm((f) => ({ ...f, label: e.target.value }))}
                    placeholder="Izoh (Call-markaz)"
                  />
                  <button className="btn" disabled={busy}>
                    +
                  </button>
                </div>
                {error && <div className="error-text">{error}</div>}
              </div>
            )}
          </ActionForm>
        </div>

        <div className="card">
          <div className="card-title">Manzillar (ofislar)</div>
          {company.locations.length === 0 && <div className="empty">Manzil qo‘shilmagan</div>}
          {company.locations.map((location) => (
            <div className="list-row" key={location.id}>
              <span>
                <b style={{ fontSize: 14 }}>{location.name}</b>{' '}
                <span className="muted">{location.address}</span>{' '}
                {location.map_url && (
                  <a href={location.map_url} target="_blank" rel="noreferrer">
                    xarita
                  </a>
                )}
              </span>
              <button className="btn ghost sm" onClick={() => deleteLocation.mutate(location.id)}>
                O‘chirish
              </button>
            </div>
          ))}
          <ActionForm
            onSubmit={async () => {
              await api('/company/locations', { body: locationForm })
              setLocationForm({ name: '', address: '', map_url: '' })
              invalidate()
            }}
          >
            {(busy, error) => (
              <div style={{ marginTop: 12 }}>
                <Field label="Nomi">
                  <input
                    className="input"
                    value={locationForm.name}
                    onChange={(e) => setLocationForm((f) => ({ ...f, name: e.target.value }))}
                    placeholder="Bosh ofis"
                    required
                    minLength={2}
                  />
                </Field>
                <Field label="Manzil">
                  <input
                    className="input"
                    value={locationForm.address}
                    onChange={(e) => setLocationForm((f) => ({ ...f, address: e.target.value }))}
                    placeholder="Toshkent, Yunusobod 4-mavze"
                  />
                </Field>
                <Field label="Xarita havolasi (ixtiyoriy)">
                  <input
                    className="input"
                    value={locationForm.map_url}
                    onChange={(e) => setLocationForm((f) => ({ ...f, map_url: e.target.value }))}
                    placeholder="https://maps.google.com/..."
                  />
                </Field>
                {error && <div className="error-text">{error}</div>}
                <button className="btn" disabled={busy}>
                  Manzil qo‘shish
                </button>
              </div>
            )}
          </ActionForm>
        </div>
      </div>
    </>
  )
}
