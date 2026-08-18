import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { EventPhase, SaleEvent } from '../api/types'
import { ActionForm, Field, Modal, Spinner, useToast } from '../components/ui'
import { formatDateTime, isoToLocalInput, localInputToIso } from '../lib/format'

export const PHASE_LABEL: Record<EventPhase, { text: string; tone: string }> = {
  registration: { text: 'Ro‘yxat ochiq', tone: 'blue' },
  checkin: { text: 'Skanerlash davom etmoqda', tone: 'amber' },
  queue: { text: 'Navbat ishlamoqda', tone: 'teal' },
  closed: { text: 'Yopilgan', tone: 'dim' },
}

export default function EventsPage() {
  const queryClient = useQueryClient()
  const toast = useToast()
  const { data: events, isLoading } = useQuery({
    queryKey: ['events'],
    queryFn: () => api<SaleEvent[]>('/events'),
  })
  const [editing, setEditing] = useState<SaleEvent | 'new' | null>(null)
  const [form, setForm] = useState({ name: '', starts_at: '', checkin_until: '' })

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
    setForm({ name: '', starts_at: '', checkin_until: '' })
    setEditing('new')
  }
  const openEdit = (event: SaleEvent) => {
    setForm({
      name: event.name,
      starts_at: isoToLocalInput(event.starts_at),
      checkin_until: isoToLocalInput(event.checkin_until),
    })
    setEditing(event)
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
        <button className="btn" onClick={openNew}>
          + Tadbir qo‘shish
        </button>
      </div>

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
                          className="btn coral sm"
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
                starts_at: localInputToIso(form.starts_at),
                checkin_until: localInputToIso(form.checkin_until),
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
                <Field label="Sotuv boshlanish vaqti">
                  <input
                    className="input"
                    type="datetime-local"
                    value={form.starts_at}
                    onChange={(e) => setForm((f) => ({ ...f, starts_at: e.target.value }))}
                    required
                  />
                </Field>
                <Field label="QR skanerlash tugash vaqti (navbat shu paytda boshlanadi)">
                  <input
                    className="input"
                    type="datetime-local"
                    value={form.checkin_until}
                    onChange={(e) => setForm((f) => ({ ...f, checkin_until: e.target.value }))}
                    required
                  />
                </Field>
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
