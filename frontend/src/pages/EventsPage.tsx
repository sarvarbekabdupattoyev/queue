import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import type { Branch, Desk, EventPhase, SaleEvent, User } from '../api/types'
import { useCompany } from '../components/DashboardLayout'
import {
  IconCalendar,
  IconCheck,
  IconChevronRight,
  IconMapPin,
  IconPlus,
} from '../components/icons'
import { ActionForm, EmptyState, Field, Modal, Spinner, useConfirm, useToast } from '../components/ui'
import { formatDateTime, isoToTashkentParts, tashkentPartsToIso } from '../lib/format'

export const PHASE_LABEL: Record<EventPhase, { text: string; tone: string }> = {
  announced: { text: 'Ro‘yxat boshlanmagan', tone: 'dim' },
  registration: { text: 'Ro‘yxat davri', tone: 'blue' },
  checkin: { text: 'QR skanerlash davri', tone: 'amber' },
  queue: { text: 'Sotuv davom etmoqda', tone: 'teal' },
  hold: { text: 'Sotuv to‘xtatib turilgan', tone: 'amber' },
  ended: { text: 'Sotuv yakunlandi', tone: 'dim' },
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
  reg_date: string
  reg_time: string
  starts_date: string
  starts_time: string
  checkin_date: string
  checkin_time: string
  sale_date: string
  sale_time: string
  branch_ids: number[]
}

const EMPTY_FORM: EventForm = {
  name: '',
  reg_date: '',
  reg_time: '08:00',
  starts_date: '',
  starts_time: '08:00',
  checkin_date: '',
  checkin_time: '10:00',
  sale_date: '',
  sale_time: '10:00',
  branch_ids: [],
}

export default function EventsPage() {
  const queryClient = useQueryClient()
  const toast = useToast()
  const confirm = useConfirm()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
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
  const setupReady = setupLoaded && setupSteps.every((s) => s.done)

  const openNew = () => {
    if (!setupReady) {
      toast('Avval tayyorgarlik qadamlarini bajaring', true)
      return
    }
    setForm({ ...EMPTY_FORM, branch_ids: (branches ?? []).map((b) => b.id) })
    setEditing('new')
  }

  // The topbar CTA lands here with ?new=1. On a cold navigation the setup
  // queries are still loading, so wait for them before consuming the param —
  // clearing it first would swallow the request and open nothing.
  useEffect(() => {
    if (!searchParams.get('new') || !setupLoaded) return
    setSearchParams({}, { replace: true })
    if (!setupReady) {
      toast('Avval tayyorgarlik qadamlarini bajaring', true)
      return
    }
    setForm({ ...EMPTY_FORM, branch_ids: (branches ?? []).map((b) => b.id) })
    setEditing('new')
    // `branches` is read once when the CTA fires; listing it would reopen the
    // dialog behind the user whenever the branch list refetches
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams, setSearchParams, setupLoaded, setupReady, toast])

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

  const openEdit = (event: SaleEvent) => {
    const reg = isoToTashkentParts(event.registration_starts_at)
    const starts = isoToTashkentParts(event.starts_at)
    const checkin = isoToTashkentParts(event.checkin_until)
    const sale = isoToTashkentParts(event.sale_starts_at)
    setForm({
      name: event.name,
      reg_date: reg.date,
      reg_time: reg.time,
      starts_date: starts.date,
      starts_time: starts.time,
      checkin_date: checkin.date,
      checkin_time: checkin.time,
      sale_date: sale.date,
      sale_time: sale.time,
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
  const confirmRemove = async (event: SaleEvent) => {
    if (
      await confirm({
        title: `«${event.name}» o‘chirilsinmi?`,
        description: 'Tadbir bilan birga uning barcha navbatlari ham o‘chadi. Bu amalni qaytarib bo‘lmaydi.',
      })
    )
      remove.mutate(event)
  }

  const branchNames = (event: SaleEvent) => event.branches.map((b) => b.name).join(', ')

  return (
    <>
      <div className="page-actions">
        <span className="hint">
          Uch davr: botda ro‘yxat → QR skanerlash → sotuv. Ro‘yxat belgilangan vaqtda ochiladi —
          undan oldin bot faqat ma’lumot beradi; ochilgach sotuv yakunlanguncha yopilmaydi,
          kechikkanlar navbat oxiriga qo‘shiladi. Yangi tadbir — yuqoridagi tugma orqali.
        </span>
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
                    <th>QR skanerlash</th>
                    <th>Sotuv boshlanishi</th>
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
                          {!!event.branches.length && (
                            <span className="cell-sub">
                              <IconMapPin size={11} style={{ verticalAlign: -1 }} />{' '}
                              {branchNames(event)}
                            </span>
                          )}
                        </td>
                        <td className="muted">{formatDateTime(event.starts_at)}</td>
                        <td className="muted">{formatDateTime(event.sale_starts_at)}</td>
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
                          {event.branches.length ? ` · ${branchNames(event)}` : ''}
                        </span>
                      </span>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, flex: '0 0 auto' }}>
                        <span className={`badge ${phase.tone}`}>{phase.text}</span>
                        <IconChevronRight size={15} className="muted" />
                      </span>
                    </span>
                    <span className="foot">
                      <span>Sotuv: {formatDateTime(event.sale_starts_at)}</span>
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
          description="Uch davr: 1) botda ro‘yxat, 2) QR skanerlash, 3) sotuv. Barcha vaqtlar Toshkent vaqti, 24 soatlik."
          onClose={() => setEditing(null)}
        >
          <ActionForm
            onSubmit={async () => {
              const payload = {
                name: form.name,
                registration_starts_at: tashkentPartsToIso(form.reg_date, form.reg_time),
                starts_at: tashkentPartsToIso(form.starts_date, form.starts_time),
                checkin_until: tashkentPartsToIso(form.checkin_date, form.checkin_time),
                sale_starts_at: tashkentPartsToIso(form.sale_date, form.sale_time),
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

                <div className="card-title" style={{ marginTop: 4 }}>1-davr · Ro‘yxatdan o‘tish</div>
                <p className="hint" style={{ marginTop: -4 }}>
                  Ro‘yxat shu vaqtda ochiladi: mijozlar botda ro‘yxatdan o‘tib QR va kod oladi.
                  Undan oldin bot sotuv boshlanmaganini aytadi va navbat tartibi, manzillar
                  hamda aloqa raqamlari haqida ma’lumot beradi. Ochilgan ro‘yxat sotuv
                  yakunlanguncha yopilmaydi.
                </p>
                <TashkentTimeField
                  label="Ro‘yxat boshlanishi"
                  date={form.reg_date}
                  time={form.reg_time}
                  onDate={(v) =>
                    setForm((f) => ({
                      ...f,
                      reg_date: v,
                      starts_date: f.starts_date || v,
                      checkin_date: f.checkin_date || v,
                      sale_date: f.sale_date || v,
                    }))
                  }
                  onTime={(v) => setForm((f) => ({ ...f, reg_time: v }))}
                />

                <div className="card-title" style={{ marginTop: 4 }}>2-davr · QR skanerlash</div>
                <p className="hint" style={{ marginTop: -4 }}>
                  Qabulxonada QR belgilash davri. Bu vaqt tugagach ham skanerlash to‘xtamaydi —
                  keyin kelganlar navbat oxiriga qo‘shiladi.
                </p>
                <TashkentTimeField
                  label="Skanerlash boshlanishi"
                  date={form.starts_date}
                  time={form.starts_time}
                  onDate={(v) => setForm((f) => ({ ...f, starts_date: v }))}
                  onTime={(v) => setForm((f) => ({ ...f, starts_time: v }))}
                />
                <TashkentTimeField
                  label="Skanerlash tugashi"
                  date={form.checkin_date}
                  time={form.checkin_time}
                  onDate={(v) => setForm((f) => ({ ...f, checkin_date: v }))}
                  onTime={(v) => setForm((f) => ({ ...f, checkin_time: v }))}
                />

                <div className="card-title" style={{ marginTop: 4 }}>3-davr · Sotuv</div>
                <p className="hint" style={{ marginTop: -4 }}>
                  Faqat boshlanish vaqti kiritiladi. Sotuv navbatdagi barcha mijozlar
                  yakunlangach o‘zi tugaydi yoki tadbir sahifasidan qo‘lda yakunlanadi;
                  uni vaqtincha to‘xtatib turish (pauza) ham mumkin.
                </p>
                <TashkentTimeField
                  label="Sotuv boshlanishi"
                  date={form.sale_date}
                  time={form.sale_time}
                  onDate={(v) => setForm((f) => ({ ...f, sale_date: v }))}
                  onTime={(v) => setForm((f) => ({ ...f, sale_time: v }))}
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
