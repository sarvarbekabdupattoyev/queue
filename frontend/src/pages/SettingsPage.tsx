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

  const deleteBot = useMutation({
    mutationFn: (id: number) => api(`/company/bots/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      invalidate()
      toast('Bot o‘chirildi')
    },
    onError: (e: Error) => toast(e.message, true),
  })
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
          <div className="card-title">
            <span>Telegram botlar</span>
            <span className="mono">
              {company.bots.length}/{company.max_bots}
            </span>
          </div>
          {company.bots.length === 0 ? (
            <p className="hint" style={{ marginBottom: 10 }}>
              Mijozlar ro‘yxatdan o‘tishi uchun bot kerak: Telegramda <b>@BotFather</b> ga{' '}
              <code>/newbot</code> yozing va olingan tokenni shu yerga qo‘ying.
            </p>
          ) : (
            company.bots.map((bot) => (
              <div className="list-row" key={bot.id}>
                <span>
                  {bot.username ? (
                    <a href={`https://t.me/${bot.username}`} target="_blank" rel="noreferrer">
                      @{bot.username}
                    </a>
                  ) : (
                    <span className="badge amber">token saqlangan, bot hozircha ishga tushmagan</span>
                  )}
                </span>
                <button
                  className="btn danger-ghost sm"
                  onClick={() => {
                    if (
                      window.confirm(
                        `${bot.username ? `@${bot.username}` : 'Bot'} o‘chirilsinmi? U orqali yozilgan mijozlarga xabarlar boshqa bot orqali yetmasligi mumkin.`,
                      )
                    )
                      deleteBot.mutate(bot.id)
                  }}
                >
                  O‘chirish
                </button>
              </div>
            ))
          )}
          {company.bots.length < company.max_bots && (
            <ActionForm
              onSubmit={async () => {
                await api('/company/bots', { body: { token: botToken } })
                setBotToken('')
                invalidate()
                toast('Bot ulandi')
              }}
            >
              {(busy, error) => (
                <div style={{ marginTop: 10 }}>
                  <Field label={company.bots.length === 0 ? 'Bot token' : 'Qo‘shimcha bot tokeni'}>
                    <input
                      className="input"
                      value={botToken}
                      onChange={(e) => setBotToken(e.target.value)}
                      placeholder="123456789:AAH..."
                      required
                      minLength={10}
                    />
                  </Field>
                  {error && <div className="error-text">{error}</div>}
                  <button className="btn" disabled={busy}>
                    {busy ? 'Tekshirilmoqda…' : 'Bot qo‘shish'}
                  </button>
                </div>
              )}
            </ActionForm>
          )}
          <p className="hint" style={{ marginTop: 12 }}>
            <b>Katta oqim kutilyaptimi?</b> Telegram bitta botga sekundiga ~30 ta xabar ruxsat
            beradi. Ro‘yxatdan o‘tish kunida daqiqasiga 10 000 tagacha ariza kelishi mumkin —
            buning uchun {company.max_bots} tagacha bot ulang: ularning hammasi bitta navbat uchun
            parallel ishlaydi. E’lonlaringizda bir nechta bot havolasini tarqating, mijozlar
            bo‘linib yoziladi. Har bir mijozga xabarlar o‘zi yozilgan bot orqali boradi.
          </p>
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
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  <input
                    className="input"
                    style={{ flex: '1 1 150px', width: 'auto' }}
                    value={phoneForm.phone}
                    onChange={(e) => setPhoneForm((f) => ({ ...f, phone: e.target.value }))}
                    placeholder="+998 71 200 50 50"
                    required
                  />
                  <input
                    className="input"
                    style={{ flex: '1 1 130px', width: 'auto' }}
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
