import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import type { Branch, EventPhase, SaleEvent } from '../api/types'
import { IconCalendar, IconChevronRight, IconMapPin, IconPlus } from '../components/icons'
import { ActionForm, EmptyState, Field, Modal, Spinner, useConfirm, useToast } from '../components/ui'
import { formatDateTime, isoToLocalInput, localInputToIso } from '../lib/format'

export const PHASE_LABEL: Record<EventPhase, { text: string; tone: string }> = {
  registration: { text: 'Ro‘yxat ochiq', tone: 'blue' },
  checkin: { text: 'Skanerlash davom etmoqda', tone: 'amber' },
  queue: { text: 'Navbat ishlamoqda', tone: 'teal' },
  closed: { text: 'Yopilgan', tone: 'dim' },
}

const EMPTY_FORM = { name: '', starts_at: '', checkin_until: '', branch_id: '' }

export default function EventsPage() {
  const queryClient = useQueryClient()
  const toast = useToast()
  const confirm = useConfirm()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const { data: events, isLoading } = useQuery({
    queryKey: ['events'],
    queryFn: () => api<SaleEvent[]>('/events'),
  })
  const { data: branches } = useQuery({
    queryKey: ['branches'],
    queryFn: () => api<Branch[]>('/branches'),
  })
  const [editing, setEditing] = useState<SaleEvent | 'new' | null>(null)
  const [form, setForm] = useState(EMPTY_FORM)

  // the topbar CTA lands here with ?new=1 — open the create dialog once
  useEffect(() => {
    if (searchParams.get('new')) {
      setForm(EMPTY_FORM)
      setEditing('new')
      setSearchParams({}, { replace: true })
    }
  }, [searchParams, setSearchParams])

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
    setForm(EMPTY_FORM)
    setEditing('new')
  }
  const openEdit = (event: SaleEvent) => {
    setForm({
      name: event.name,
      starts_at: isoToLocalInput(event.starts_at),
      checkin_until: isoToLocalInput(event.checkin_until),
      branch_id: event.branch_id?.toString() ?? '',
    })
    setEditing(event)
  }
  const confirmRemove = async (event: SaleEvent) => {
    if (
      await confirm({
        title: `«${event.name}» o‘chirilsinmi?`,
        description: 'Tadbir bilan birga uning barcha navbatlari ham o‘chadi. Bu amalni qaytarib bo‘lmaydi.',
      })
    )
      remove.mutate(event)
  }

  return (
    <>
      <div className="page-actions">
        <span className="hint">
          Bot tadbir boshlanishidan skanerlash tugashigacha raqam beradi; keyin navbat ro‘yxat
          vaqti bo‘yicha ishlaydi. Yangi tadbir — yuqoridagi tugma orqali.
        </span>
      </div>

      <div className="card">
        {isLoading ? (
          <Spinner />
        ) : !events?.length ? (
          <EmptyState
            icon={IconCalendar}
            action={
              <button className="btn" onClick={openNew}>
                <IconPlus size={15} /> Birinchi tadbirni qo‘shish
              </button>
            }
          >
            Hozircha tadbirlar yo‘q. Sotuv kunini qo‘shing — mijozlar Telegram bot orqali
            ro‘yxatdan o‘tadi.
          </EmptyState>
        ) : (
          <>
            <div className="table-wrap only-desktop">
              <table className="table">
                <thead>
                  <tr>
                    <th>Tadbir</th>
                    <th>Boshlanish</th>
                    <th>Skanerlash tugashi</th>
                    <th>Holat</th>
                    <th style={{ textAlign: 'right' }}>Ro‘yxat / Kelgan</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {events.map((event) => {
                    const phase = PHASE_LABEL[event.phase]
                    return (
                      <tr
                        key={event.id}
                        className="rowlink"
                        onClick={() => navigate(`/dashboard/events/${event.id}`)}
                      >
                        <td>
                          <Link
                            to={`/dashboard/events/${event.id}`}
                            className="cell-main"
                            onClick={(e) => e.stopPropagation()}
                          >
                            {event.name}
                          </Link>
                          {event.branch_name && (
                            <span className="cell-sub">
                              <IconMapPin size={11} style={{ verticalAlign: -1 }} /> {event.branch_name}
                            </span>
                          )}
                        </td>
                        <td className="muted">{formatDateTime(event.starts_at)}</td>
                        <td className="muted">{formatDateTime(event.checkin_until)}</td>
                        <td>
                          <span className={`badge ${phase.tone}`}>{phase.text}</span>
                        </td>
                        <td className="mono" style={{ textAlign: 'right' }}>
                          {event.ticket_count} / {event.checked_in_count}
                        </td>
                        <td onClick={(e) => e.stopPropagation()}>
                          <span className="row-actions">
                            <button className="btn ghost sm" onClick={() => openEdit(event)}>
                              Tahrirlash
                            </button>
                            <button className="btn ghost sm" onClick={() => toggleActive.mutate(event)}>
                              {event.is_active ? 'Yopish' : 'Ochish'}
                            </button>
                            <button className="btn danger-ghost sm" onClick={() => void confirmRemove(event)}>
                              O‘chirish
                            </button>
                          </span>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            <div className="stack-list only-mobile">
              {events.map((event) => {
                const phase = PHASE_LABEL[event.phase]
                return (
                  <Link className="stack-item" to={`/dashboard/events/${event.id}`} key={event.id}>
                    <span className="top">
                      <span style={{ minWidth: 0 }}>
                        <span className="cell-main">{event.name}</span>
                        <span className="cell-sub">
                          {formatDateTime(event.starts_at)}
                          {event.branch_name ? ` · ${event.branch_name}` : ''}
                        </span>
                      </span>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, flex: '0 0 auto' }}>
                        <span className={`badge ${phase.tone}`}>{phase.text}</span>
                        <IconChevronRight size={15} className="muted" />
                      </span>
                    </span>
                    <span className="foot">
                      <span>Skanerlash: {formatDateTime(event.checkin_until)}</span>
                      <span className="mono">
                        {event.ticket_count} / {event.checked_in_count}
                      </span>
                    </span>
                  </Link>
                )
              })}
            </div>
          </>
        )}
      </div>

      {editing && (
        <Modal
          title={editing === 'new' ? 'Yangi sotuv tadbiri' : 'Tadbirni tahrirlash'}
          description="Skanerlash tugagach chaqiruv ochiladi — tartib botdan ro‘yxatdan o‘tish vaqti bo‘yicha."
          onClose={() => setEditing(null)}
        >
          <ActionForm
            onSubmit={async () => {
              const branchPart =
                editing === 'new'
                  ? form.branch_id
                    ? { branch_id: Number(form.branch_id) }
                    : {}
                  : form.branch_id
                    ? { branch_id: Number(form.branch_id) }
                    : { clear_branch: true }
              const payload = {
                name: form.name,
                starts_at: localInputToIso(form.starts_at),
                checkin_until: localInputToIso(form.checkin_until),
                ...branchPart,
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
                {!!branches?.length && (
                  <Field label="Filial (ixtiyoriy — bot bitta, filial faqat manzilni bildiradi)">
                    <select
                      className="input"
                      value={form.branch_id}
                      onChange={(e) => setForm((f) => ({ ...f, branch_id: e.target.value }))}
                    >
                      <option value="">— filialsiz —</option>
                      {branches.map((b) => (
                        <option key={b.id} value={b.id}>
                          {b.name}
                        </option>
                      ))}
                    </select>
                  </Field>
                )}
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
