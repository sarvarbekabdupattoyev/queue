import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, getToken, wsUrl } from '../api/client'
import type { SaleEvent, StaffState, Ticket, TicketStatus } from '../api/types'
import { CopyButton, Spinner, useToast } from '../components/ui'
import { formatDateTime, formatLongCountdown, prettyPhone } from '../lib/format'
import { useLiveState, useTick } from '../lib/useLiveState'
import { PHASE_LABEL } from './EventsPage'

const STATUS_LABEL: Record<TicketStatus, { text: string; tone: string }> = {
  registered: { text: 'Ro‘yxatda', tone: 'dim' },
  checked_in: { text: 'Keldi', tone: 'blue' },
  called: { text: 'Chaqirildi', tone: 'amber' },
  serving: { text: 'Xizmatda', tone: 'teal' },
  done: { text: 'Yakunlandi', tone: 'teal' },
  skipped: { text: 'Kelmadi', tone: 'coral' },
  cancelled: { text: 'Bekor', tone: 'coral' },
}

export default function EventDetailPage() {
  const { eventId } = useParams()
  const queryClient = useQueryClient()
  const toast = useToast()
  const now = useTick()
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('')

  const { data: event } = useQuery({
    queryKey: ['event', eventId],
    queryFn: () => api<SaleEvent>(`/events/${eventId}`),
  })
  const { state } = useLiveState<StaffState>(
    eventId ? wsUrl(`/ws/staff/${eventId}?token=${getToken()}`) : null,
    eventId ? () => api<StaffState>(`/events/${eventId}/state`) : null,
  )
  const ticketsQuery = useQuery({
    queryKey: ['tickets', eventId, search, statusFilter],
    queryFn: () =>
      api<Ticket[]>(
        `/events/${eventId}/tickets?q=${encodeURIComponent(search)}${
          statusFilter ? `&ticket_status=${statusFilter}` : ''
        }`,
      ),
    enabled: !!eventId,
    refetchInterval: 15000,
  })

  const seed = useMutation({
    mutationFn: () => api(`/events/${eventId}/seed`, { body: { count: 10 } }),
    onSuccess: () => {
      toast('10 ta sinov mijozi qo‘shildi')
      queryClient.invalidateQueries({ queryKey: ['tickets', eventId] })
    },
    onError: (e: Error) => toast(e.message, true),
  })
  const cancelTicket = useMutation({
    mutationFn: (number: number) => api(`/queue/${eventId}/cancel`, { body: { number } }),
    onSuccess: () => {
      toast('Navbat bekor qilindi')
      queryClient.invalidateQueries({ queryKey: ['tickets', eventId] })
    },
    onError: (e: Error) => toast(e.message, true),
  })
  const checkin = useMutation({
    mutationFn: (number: number) => api(`/queue/${eventId}/checkin`, { body: { number } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['tickets', eventId] }),
    onError: (e: Error) => toast(e.message, true),
  })

  const displayLink = useMemo(
    () => (event ? `${window.location.origin}/display/${event.display_code}` : ''),
    [event],
  )
  if (!event) return <Spinner />
  const phase = PHASE_LABEL[event.phase]
  const untilQueue = new Date(event.checkin_until).getTime() - now
  const stats = state?.stats

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{event.name}</h1>
          <div className="sub">
            Boshlanish: {formatDateTime(event.starts_at)} · Skanerlash tugashi:{' '}
            {formatDateTime(event.checkin_until)} · <span className={`badge ${phase.tone}`}>{phase.text}</span>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <Link className="btn ghost sm" to="/scanner">
            Skaner sahifasi
          </Link>
          <Link className="btn ghost sm" to="/manager">
            Menejer paneli
          </Link>
          <a className="btn ghost sm" href={displayLink} target="_blank" rel="noreferrer">
            Ofis ekrani ↗
          </a>
          <CopyButton text={displayLink} label="Ekran havolasini nusxalash" />
        </div>
      </div>

      {event.is_active && untilQueue > 0 && (
        <div className="card" style={{ borderColor: 'var(--amber)' }}>
          <div className="card-title">Navbat boshlanishiga qoldi</div>
          <div className="mono" style={{ fontSize: 30, color: 'var(--amber)' }}>
            {formatLongCountdown(untilQueue)}
          </div>
          <p className="hint" style={{ marginTop: 6 }}>
            Skanerlash tugagach chaqiruv ochiladi — tartib botdan ro‘yxatdan o‘tish vaqti bo‘yicha.
          </p>
        </div>
      )}

      <div className="card">
        <div className="card-title">
          <span>Jonli holat</span>
        </div>
        <div className="stat-row">
          <div className="stat">
            <b>{stats?.registered ?? event.ticket_count}</b>
            <span>Yozilgan</span>
          </div>
          <div className="stat">
            <b>{stats?.arrived ?? event.checked_in_count}</b>
            <span>Kelgan</span>
          </div>
          <div className="stat">
            <b>{stats?.waiting ?? '—'}</b>
            <span>Kutmoqda</span>
          </div>
          <div className="stat">
            <b>{stats?.done ?? '—'}</b>
            <span>Yakunlandi</span>
          </div>
          <div className="stat">
            <b>{stats?.skipped ?? '—'}</b>
            <span>Kelmadi</span>
          </div>
        </div>
        {!!state?.active?.length && (
          <div style={{ marginTop: 14 }}>
            {state.active.map((t) => (
              <div className="list-row" key={t.id}>
                <span>
                  <b>{t.number}</b> {t.name}
                </span>
                <span className="muted">
                  {t.desk_number}-stol · {t.status === 'serving' ? 'xizmatda' : 'chaqirildi'}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="card">
        <div className="card-title">
          <span>Mijozlar ro‘yxati</span>
          <span style={{ display: 'flex', gap: 8 }}>
            <button className="btn ghost sm" onClick={() => seed.mutate()} disabled={seed.isPending}>
              +10 sinov mijozi
            </button>
          </span>
        </div>
        <div style={{ display: 'flex', gap: 10, marginBottom: 12, flexWrap: 'wrap' }}>
          <input
            className="input"
            style={{ maxWidth: 260 }}
            placeholder="Qidirish: ism, telefon, raqam"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <select
            className="input"
            style={{ maxWidth: 200 }}
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="">Barcha holatlar</option>
            {Object.entries(STATUS_LABEL).map(([value, label]) => (
              <option key={value} value={value}>
                {label.text}
              </option>
            ))}
          </select>
        </div>
        {ticketsQuery.isLoading ? (
          <Spinner />
        ) : !ticketsQuery.data?.length ? (
          <div className="empty">Mijozlar topilmadi. Bot orqali ro‘yxatdan o‘tishlarini kuting.</div>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>№</th>
                  <th>Mijoz</th>
                  <th>Telefon</th>
                  <th>Ro‘yxat vaqti</th>
                  <th>Holat</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {ticketsQuery.data.map((ticket) => {
                  const label = STATUS_LABEL[ticket.status]
                  return (
                    <tr key={ticket.id}>
                      <td className="num">{ticket.number}</td>
                      <td>
                        {ticket.first_name} {ticket.last_name}
                        {ticket.source === 'seed' && <span className="badge dim"> sinov</span>}
                      </td>
                      <td className="muted">{prettyPhone(ticket.phone)}</td>
                      <td className="muted">{formatDateTime(ticket.registered_at)}</td>
                      <td>
                        <span className={`badge ${label.tone}`}>{label.text}</span>
                        {ticket.late && <span className="badge amber"> kun oxiri</span>}
                      </td>
                      <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                        {(ticket.status === 'registered' || ticket.status === 'skipped') && (
                          <button className="btn ghost sm" onClick={() => checkin.mutate(ticket.number)}>
                            Keldi
                          </button>
                        )}{' '}
                        {!['done', 'cancelled'].includes(ticket.status) && (
                          <button
                            className="btn coral sm"
                            onClick={() => {
                              if (window.confirm(`№${ticket.number} bekor qilinsinmi?`))
                                cancelTicket.mutate(ticket.number)
                            }}
                          >
                            Bekor
                          </button>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  )
}
