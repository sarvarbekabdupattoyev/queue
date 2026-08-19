import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { Branch, Desk, EventPhase, SaleEvent, User } from '../api/types'
import { useCompany } from '../components/DashboardLayout'
import { IconCheck, IconPlus } from '../components/icons'
import { ActionForm, Field, Modal, Spinner, useToast } from '../components/ui'
import { formatDateTime, isoToTashkentParts, tashkentPartsToIso } from '../lib/format'

export const PHASE_LABEL: Record<EventPhase, { text: string; tone: string }> = {
  registration: { text: 'Ro‘yxat ochiq', tone: 'blue' },
  checkin: { text: 'Skanerlash davom etmoqda', tone: 'amber' },
  queue: { text: 'Navbat ishlamoqda', tone: 'teal' },
  closed: { text: 'Yopilgan', tone: 'dim' },
}

const HOURS = Array.from({ length: 24 }, (_, i) => String(i).padStart(2, '0'))
const MINUTES = Array.from({ length: 12 }, (_, i) => String(i * 5).padStart(2, '0'))

/** Date + 24-hour time picker fixed to Tashkent time — no AM/PM ever,
 * whatever the operator's browser locale is. */
function TashkentTimeField({
  label,
  date,
  time,
  onDate,
  onTime,
}: {
  label: string
  date: string
  time: string
  onDate: (v: string) => void
  onTime: (v: string) => void
}) {
  const [hour, minute] = time.split(':')
  const minutes = MINUTES.includes(minute) ? MINUTES : [...MINUTES, minute].sort()
  return (
    <div className="field">
      <span>{label}</span>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <input
          className="input"
          type="date"
          value={date}
          onChange={(e) => onDate(e.target.value)}
          aria-label={`${label} — sana`}
          required
        />
        <select
          className="input"
          style={{ width: 'auto' }}
          value={hour}
          onChange={(e) => onTime(`${e.target.value}:${minute}`)}
          aria-label={`${label} — soat (24 soatlik)`}
        >
          {HOURS.map((h) => (
            <option key={h} value={h}>
              {h}
            </option>
          ))}
        </select>
        <span aria-hidden="true">:</span>
        <select
          className="input"
          style={{ width: 'auto' }}
          value={minute}
          onChange={(e) => onTime(`${hour}:${e.target.value}`)}
          aria-label={`${label} — daqiqa`}
        >
          {minutes.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
      </div>
    </div>
  )
}

interface EventForm {
  name: string
  starts_date: string
  starts_time: string
  checkin_date: string
  checkin_time: string
  branch_ids: number[]
}

const EMPTY_FORM: EventForm = {
  name: '',
  starts_date: '',
  starts_time: '09:00',
  checkin_date: '',
  checkin_time: '10:00',
  branch_ids: [],
}

export default function EventsPage() {
  const queryClient = useQueryClient()
  const toast = useToast()
  const { data: company } = useCompany()
  const { data: events, isLoading } = useQuery({
    queryKey: ['events'],
    queryFn: () => api<SaleEvent[]>('/events'),
  })
  const { data: branches } = useQuery({
    queryKey: ['branches'],
    queryFn: () => api<Branch[]>('/branches'),
  })
  const { data: employees } = useQuery({
    queryKey: ['employees'],
    queryFn: () => api<User[]>('/employees'),
  })
  const { data: desks } = useQuery({ queryKey: ['desks'], queryFn: () => api<Desk[]>('/desks') })
  const [editing, setEditing] = useState<SaleEvent | 'new' | null>(null)
  const [form, setForm] = useState<EventForm>(EMPTY_FORM)

  const hasBranches = (branches?.length ?? 0) > 0

  // the setup flow the product expects: settings (bot) → branches (if any) →
  // managers → desks; only then a tadbir makes sense
  const setupSteps = [
    {
      done: !!company?.has_bot_token,
      label: 'Sozlamalarda Telegram bot ulang',
      to: '/dashboard/settings',
    },
    {
      done: (employees ?? []).some((e) => e.role === 'manager' && e.is_active),
      label: hasBranches ? 'Har bir filialga menejer qo‘shing' : 'Menejer qo‘shing',
      to: '/dashboard/employees',
    },
    {
      done: (desks?.length ?? 0) > 0,
      label: hasBranches
        ? 'Filiallarga stollar yaratib, menejer biriktiring'
        : 'Stol yaratib, menejer biriktiring',
      to: '/dashboard/desks',
    },
  ]
  const setupLoaded = company !== undefined && employees !== undefined && desks !== undefined
  const missingSteps = setupLoaded ? setupSteps.filter((s) => !s.done) : []
  const setupReady = setupLoaded && missingSteps.length === 0

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['events'] })
  const toggleActive = useMutation({
    mutationFn: (event: SaleEvent) =>
      api<SaleEvent>(`/events/${event.id}`, {
        method: 'PATCH',
        body: { is_active: !event.is_active },
      }),
    onSuccess: invalidate,
    onError: (e: Error) => toast(e.message, true),
  })
  const remove = useMutation({
    mutationFn: (event: SaleEvent) => api(`/events/${event.id}`, { method: 'DELETE' }),
    onSuccess: () => {
      invalidate()
      toast('Tadbir o‘chirildi')
    },
    onError: (e: Error) => toast(e.message, true),
  })

  const openNew = () => {
    setForm({ ...EMPTY_FORM, branch_ids: (branches ?? []).map((b) => b.id) })
    setEditing('new')
  }
  const openEdit = (event: SaleEvent) => {
    const starts = isoToTashkentParts(event.starts_at)
    const checkin = isoToTashkentParts(event.checkin_until)
    setForm({
      name: event.name,
      starts_date: starts.date,
      starts_time: starts.time,
      checkin_date: checkin.date,
      checkin_time: checkin.time,
      branch_ids: event.branches.map((b) => b.id),
    })
    setEditing(event)
  }
  const toggleBranch = (id: number) => {
    setForm((f) => ({
      ...f,
      branch_ids: f.branch_ids.includes(id)
        ? f.branch_ids.filter((b) => b !== id)
        : [...f.branch_ids, id],
    }))
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Sotuv tadbirlari</h1>
          <div className="sub">
            Bot tadbir boshlanishidan skanerlash tugashigacha raqam beradi; skanerlash tugagach
            navbat ro‘yxatdan o‘tish vaqti bo‘yicha boshlanadi
          </div>
        </div>
        <button
          className="btn"
          onClick={openNew}
          disabled={!setupReady}
          title={setupReady ? undefined : 'Avval quyidagi tayyorgarlik qadamlarini bajaring'}
        >
          <IconPlus size={16} /> Tadbir qo‘shish
        </button>
      </div>

      {setupLoaded && !setupReady && (
        <div className="card" style={{ borderColor: 'var(--amber)' }}>
          <div className="card-title">Tadbir yaratishdan oldin</div>
          <p className="hint" style={{ marginBottom: 10 }}>
            Tartib: avval Sozlamalar, keyin (bo‘lsa) Filiallar, so‘ng Menejerlar va Stollar —
            shundan keyin tadbir e’lon qilinadi.
          </p>
          {setupSteps.map((step) => (
            <div className="check-row" key={step.label}>
              <span className={`lbl${step.done ? ' done-text' : ''}`}>
                <span className={`mark ${step.done ? 'done' : 'todo'}`}>
                  <IconCheck size={13} />
                </span>
                {step.label}
              </span>
              {!step.done && (
                <Link className="btn tonal sm" to={step.to}>
                  Bajarish
                </Link>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="card">
        {isLoading ? (
          <Spinner />
        ) : !events?.length ? (
          <div className="empty">
            Hozircha tadbirlar yo‘q. Sotuv kunini qo‘shing — mijozlar Telegram bot orqali
            ro‘yxatdan o‘tadi.
          </div>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Tadbir</th>
                  {hasBranches && <th>Filiallar</th>}
                  <th>Boshlanish</th>
                  <th>Skanerlash tugashi</th>
                  <th>Holat</th>
                  <th>Ro‘yxat / Kelgan</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {events.map((event) => {
                  const phase = PHASE_LABEL[event.phase]
                  return (
                    <tr key={event.id}>
                      <td>
                        <Link to={`/dashboard/events/${event.id}`} style={{ fontWeight: 600 }}>
                          {event.name}
                        </Link>
                      </td>
                      {hasBranches && (
                        <td>
                          {event.branches.length ? (
                            event.branches.map((b) => (
                              <span key={b.id} className="badge blue" style={{ marginRight: 4 }}>
                                {b.name}
                              </span>
                            ))
                          ) : (
                            <span className="muted">—</span>
                          )}
                        </td>
                      )}
                      <td className="muted">{formatDateTime(event.starts_at)}</td>
                      <td className="muted">{formatDateTime(event.checkin_until)}</td>
                      <td>
                        <span className={`badge ${phase.tone}`}>{phase.text}</span>
                      </td>
                      <td className="mono">
                        {event.ticket_count} / {event.checked_in_count}
                      </td>
                      <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                        <Link className="btn ghost sm" to={`/dashboard/events/${event.id}`}>
                          Boshqarish
                        </Link>{' '}
                        <button className="btn ghost sm" onClick={() => openEdit(event)}>
                          Tahrirlash
                        </button>{' '}
                        <button className="btn ghost sm" onClick={() => toggleActive.mutate(event)}>
                          {event.is_active ? 'Yopish' : 'Ochish'}
                        </button>{' '}
                        <button
                          className="btn danger-ghost sm"
                          onClick={() => {
                            if (
                              window.confirm(
                                `«${event.name}» va uning barcha navbatlari o‘chirilsinmi?`,
                              )
                            )
                              remove.mutate(event)
                          }}
                        >
                          O‘chirish
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {editing && (
        <Modal
          title={editing === 'new' ? 'Yangi sotuv tadbiri' : 'Tadbirni tahrirlash'}
          onClose={() => setEditing(null)}
        >
          <ActionForm
            onSubmit={async () => {
              const payload = {
                name: form.name,
                starts_at: tashkentPartsToIso(form.starts_date, form.starts_time),
                checkin_until: tashkentPartsToIso(form.checkin_date, form.checkin_time),
                branch_ids: form.branch_ids,
              }
              if (editing === 'new') await api<SaleEvent>('/events', { body: payload })
              else await api<SaleEvent>(`/events/${editing.id}`, { method: 'PATCH', body: payload })
              setEditing(null)
              invalidate()
            }}
          >
            {(busy, error) => (
              <>
                <Field label="Tadbir nomi">
                  <input
                    className="input"
                    value={form.name}
                    onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                    placeholder="Masalan: Bahor City · Sotuv kuni"
                    required
                    minLength={2}
                  />
                </Field>
                <TashkentTimeField
                  label="Sotuv boshlanish vaqti (Toshkent vaqti, 24 soatlik)"
                  date={form.starts_date}
                  time={form.starts_time}
                  onDate={(v) => setForm((f) => ({ ...f, starts_date: v, checkin_date: f.checkin_date || v }))}
                  onTime={(v) => setForm((f) => ({ ...f, starts_time: v }))}
                />
                <TashkentTimeField
                  label="QR skanerlash tugash vaqti — navbat shu paytda boshlanadi (Toshkent vaqti, 24 soatlik)"
                  date={form.checkin_date}
                  time={form.checkin_time}
                  onDate={(v) => setForm((f) => ({ ...f, checkin_date: v }))}
                  onTime={(v) => setForm((f) => ({ ...f, checkin_time: v }))}
                />
                {hasBranches && (
                  <div className="field">
                    <span>Filiallar (bir nechtasini tanlash mumkin)</span>
                    {(branches ?? []).map((b) => (
                      <label
                        key={b.id}
                        style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '4px 0' }}
                      >
                        <input
                          type="checkbox"
                          checked={form.branch_ids.includes(b.id)}
                          onChange={() => toggleBranch(b.id)}
                        />
                        <span>
                          {b.name}{' '}
                          <span className="muted">
                            · {b.desk_count} stol · {b.employee_count} xodim
                          </span>
                        </span>
                      </label>
                    ))}
                    <p className="hint">
                      Bitta tadbir bir nechta filialda o‘tadi: mijoz botda filialni tanlaydi,
                      navbat va stollar har filialda alohida yuritiladi. Tanlangan har bir
                      filialda kamida bitta stol bo‘lsin.
                    </p>
                  </div>
                )}
                <p className="hint">
                  Shu vaqtgacha kelgan mijozlar QR kodini skanerlatadi. Vaqt tugagach chaqiruv
                  boshlanadi: tartib — botdan ro‘yxatdan o‘tish vaqti bo‘yicha, faqat skanerdan
                  o‘tganlar orasida. Kechikkanlar kun oxiri navbatiga qo‘shiladi.
                </p>
                {error && <div className="error-text">{error}</div>}
                <div className="modal-actions">
                  <button type="button" className="btn ghost" onClick={() => setEditing(null)}>
                    Bekor qilish
                  </button>
                  <button className="btn" disabled={busy}>
                    Saqlash
                  </button>
                </div>
              </>
            )}
          </ActionForm>
        </Modal>
      )}
    </>
  )
}
