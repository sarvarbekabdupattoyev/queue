import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, getToken, wsUrl } from '../api/client'
import type { SaleEvent, StaffState, Ticket, TicketStatus } from '../api/types'
import { PageTitle } from '../components/DashboardLayout'
import { WalkinModal } from '../components/WalkinModal'
import { IconMapPin, IconMonitor, IconPlus, IconRefresh } from '../components/icons'
import { CopyButton, EmptyState, Spinner, useConfirm, useToast } from '../components/ui'
import { formatDateTime, formatLongCountdown, prettyPhone } from '../lib/format'
import { useDebounced, useLiveState, useTick } from '../lib/useLiveState'
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
  const confirm = useConfirm()
  const now = useTick()
  const [search, setSearch] = useState('')
  // each keystroke would otherwise be a fresh ILIKE across the event's tickets
  const debouncedSearch = useDebounced(search)
  const [statusFilter, setStatusFilter] = useState('')
  const [branchFilter, setBranchFilter] = useState('')
  const [addingWalkin, setAddingWalkin] = useState(false)

  const {
    data: event,
    isLoading: eventLoading,
    error: eventError,
    refetch: refetchEvent,
  } = useQuery({
    queryKey: ['event', eventId],
    queryFn: () => api<SaleEvent>(`/events/${eventId}`),
  })
  const { state, connected } = useLiveState<StaffState>(
    eventId ? wsUrl(`/ws/staff/${eventId}?token=${getToken()}`) : null,
    eventId ? () => api<StaffState>(`/events/${eventId}/state`) : null,
  )
  const ticketsQuery = useQuery({
    queryKey: ['tickets', eventId, debouncedSearch, statusFilter, branchFilter],
    queryFn: () =>
      api<Ticket[]>(
        `/events/${eventId}/tickets?q=${encodeURIComponent(debouncedSearch)}${
          statusFilter ? `&ticket_status=${statusFilter}` : ''
        }${branchFilter ? `&branch_id=${branchFilter}` : ''}`,
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
    mutationFn: (number: string) => api(`/queue/${eventId}/cancel`, { body: { number } }),
    onSuccess: () => {
      toast('Navbat bekor qilindi')
      queryClient.invalidateQueries({ queryKey: ['tickets', eventId] })
    },
    onError: (e: Error) => toast(e.message, true),
  })
  const checkin = useMutation({
    mutationFn: (number: string) => api(`/queue/${eventId}/checkin`, { body: { number } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['tickets', eventId] }),
    onError: (e: Error) => toast(e.message, true),
  })
  const saleAction = useMutation({
    mutationFn: (action: 'hold' | 'resume' | 'end' | 'reopen') =>
      api<SaleEvent>(`/events/${eventId}/sale`, { body: { action } }),
    onSuccess: (updated) => {
      queryClient.setQueryData(['event', eventId], updated)
      queryClient.invalidateQueries({ queryKey: ['event', eventId] })
      toast(
        updated.phase === 'ended'
          ? 'Sotuv yakunlandi'
          : updated.sale_hold
            ? 'Sotuv to‘xtatib turildi'
            : 'Sotuv davom etmoqda',
      )
    },
    onError: (e: Error) => toast(e.message, true),
  })

  const displayLink = useMemo(
    () => (event ? `${window.location.origin}/display/${event.display_code}` : ''),
    [event],
  )
  if (eventLoading) return <Spinner />
  if (eventError || !event)
    return (
      <EmptyState
        action={
          <button className="btn ghost sm" onClick={() => refetchEvent()}>
            <IconRefresh size={14} /> Qayta urinish
          </button>
        }
      >
        Tadbirni yuklab bo‘lmadi. Internetni tekshirib qayta urinib ko‘ring.
      </EmptyState>
    )
  const phase = PHASE_LABEL[event.phase]
  const untilSale = new Date(event.sale_starts_at).getTime() - now
  const stats = state?.stats
  const hasBranches = event.branches.length > 0
  const saleStarted = event.phase === 'queue' || event.phase === 'hold'

  return (
    <>
      <PageTitle title={event.name} />

      <div className="page-actions">
        <span className={`badge ${phase.tone}`}>{phase.text}</span>
        {event.branches.map((b) => (
          <span key={b.id} className="badge dim">
            <IconMapPin size={11} /> {b.name}
          </span>
        ))}
        <span className="hint hide-sm">
          Ro‘yxat {formatDateTime(event.registration_starts_at)} dan · Skanerlash{' '}
          {formatDateTime(event.starts_at)} — {formatDateTime(event.checkin_until)} · Sotuv{' '}
          {formatDateTime(event.sale_starts_at)} dan
        </span>
        <span className={`conn-chip${connected ? ' on' : ''}`}>
          <span className="dot" /> {connected ? 'jonli' : 'ulanmoqda…'}
        </span>
        <span className="push" style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <Link className="btn ghost sm" to="/scanner">
            Skaner
          </Link>
          <Link className="btn ghost sm" to="/manager">
            Menejer paneli
          </Link>
          {hasBranches ? (
            // each branch runs its own queue, so each gets its own TV board
            event.branches.map((b) => (
              <a
                key={b.id}
                className="btn ghost sm"
                href={`${displayLink}?branch=${b.id}`}
                target="_blank"
                rel="noreferrer"
              >
                <IconMonitor size={14} /> {b.name}
              </a>
            ))
          ) : (
            <a className="btn ghost sm" href={displayLink} target="_blank" rel="noreferrer">
              <IconMonitor size={14} /> Ofis ekrani
            </a>
          )}
          <CopyButton text={displayLink} label="Havola" />
        </span>
      </div>

      {event.is_active && event.sale_ended_at === null && untilSale > 0 && (
        <div className="card">
          <div className="stat-label">Sotuv boshlanishiga qoldi</div>
          <div className="stat-value" style={{ fontSize: 34, color: 'var(--amber)' }}>
            {formatLongCountdown(untilSale)}
          </div>
          <p className="hint" style={{ marginTop: 6 }}>
            Sotuv boshlanganda chaqiruv ochiladi va har bir mijozga navbat tartibi botda
            yuboriladi — tartib botdan ro‘yxatdan o‘tish vaqti bo‘yicha.
          </p>
        </div>
      )}

      {event.is_active && (saleStarted || event.phase === 'ended') && (
        <div className="card">
          <div className="card-title">
            Sotuvni boshqarish
            <span className="aux">
              {event.phase === 'hold'
                ? 'To‘xtatib turilgan — chaqiruv yopiq, skanerlash davom etadi'
                : event.phase === 'ended'
                  ? 'Yakunlangan'
                  : 'Navbat tugagach sotuv o‘zi yakunlanadi'}
            </span>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {event.phase === 'queue' && (
              <button
                className="btn tonal"
                disabled={saleAction.isPending}
                onClick={() => saleAction.mutate('hold')}
              >
                To‘xtatib turish
              </button>
            )}
            {event.phase === 'hold' && (
              <button
                className="btn"
                disabled={saleAction.isPending}
                onClick={() => saleAction.mutate('resume')}
              >
                Davom ettirish
              </button>
            )}
            {event.phase !== 'ended' ? (
              <button
                className="btn danger-ghost"
                disabled={saleAction.isPending}
                onClick={async () => {
                  if (
                    await confirm({
                      title: 'Sotuv yakunlansinmi?',
                      description:
                        'Chaqiruv va skanerlash to‘xtaydi. Kerak bo‘lsa keyin qayta ochish mumkin.',
                      confirmLabel: 'Yakunlash',
                    })
                  )
                    saleAction.mutate('end')
                }}
              >
                Sotuvni yakunlash
              </button>
            ) : (
              <button
                className="btn"
                disabled={saleAction.isPending}
                onClick={() => saleAction.mutate('reopen')}
              >
                Sotuvni qayta ochish
              </button>
            )}
          </div>
        </div>
      )}

      <div className="card">
        <div className="card-title">Jonli holat</div>
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
            <b>{stats?.contracts ?? '—'}</b>
            <span>Shartnoma tuzildi</span>
          </div>
          <div className="stat">
            <b>{stats?.no_contract ?? '—'}</b>
            <span>Shartnomasiz</span>
          </div>
          <div className="stat">
            <b>{stats?.skipped ?? '—'}</b>
            <span>Kelmadi</span>
          </div>
          <div className="stat">
            <b>{stats?.late ?? '—'}</b>
            <span>Kech kelgan</span>
          </div>
          <div className="stat">
            <b>{stats?.staff_added ?? '—'}</b>
            <span>Xodim qo‘shgan</span>
          </div>
        </div>
        {hasBranches && !!state?.by_branch?.length && (
          <div style={{ marginTop: 14 }}>
            {state.by_branch.map((b) => (
              <div className="list-row" key={b.id}>
                <span style={{ fontWeight: 600 }}>{b.name}</span>
                <span className="muted mono">
                  {b.stats.registered} yozilgan · {b.stats.arrived} kelgan · {b.stats.waiting}{' '}
                  kutmoqda · {b.stats.done} yakunlandi · {b.stats.contracts ?? 0} shartnoma
                </span>
              </div>
            ))}
          </div>
        )}
        {!!state?.active?.length && (
          <div style={{ marginTop: 14 }}>
            {state.active.map((t) => (
              <div className="list-row" key={t.id}>
                <span>
                  <b>{t.number}</b> {t.name}
                </span>
                <span className="muted">
                  {t.branch_name ? `${t.branch_name} · ` : ''}
                  {t.desk_number}-stol · {t.status === 'serving' ? 'xizmatda' : 'chaqirildi'}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="card">
        <div className="card-title">
          Mijozlar ro‘yxati
          <span className="aux" style={{ display: 'inline-flex', gap: 8 }}>
            <button
              className="btn sm"
              onClick={() => setAddingWalkin(true)}
              disabled={event.phase === 'ended' || !event.is_active}
            >
              <IconPlus size={14} /> Mijoz qo‘shish
            </button>
            <button className="btn ghost sm" onClick={() => seed.mutate()} disabled={seed.isPending}>
              +10 sinov mijozi
            </button>
          </span>
        </div>
        <div style={{ display: 'flex', gap: 10, marginBottom: 12, flexWrap: 'wrap' }}>
          <input
            className="input"
            style={{ maxWidth: 260 }}
            placeholder="Qidirish: ism, telefon, kod"
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
          {hasBranches && (
            <select
              className="input"
              style={{ maxWidth: 200 }}
              value={branchFilter}
              onChange={(e) => setBranchFilter(e.target.value)}
              aria-label="Filial bo‘yicha filtrlash"
            >
              <option value="">Barcha filiallar</option>
              {event.branches.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </select>
          )}
        </div>
        {ticketsQuery.isLoading ? (
          <Spinner />
        ) : ticketsQuery.error && !ticketsQuery.data ? (
          <div className="empty">
            Ro‘yxatni yuklab bo‘lmadi.{' '}
            <button className="btn ghost sm" onClick={() => ticketsQuery.refetch()}>
              Qayta urinish
            </button>
          </div>
        ) : !ticketsQuery.data?.length ? (
          <div className="empty">Mijozlar topilmadi. Bot orqali ro‘yxatdan o‘tishlarini kuting.</div>
        ) : (
          <>
          <div className="table-wrap only-desktop">
            <table className="table">
              <thead>
                <tr>
                  <th>№</th>
                  <th>Mijoz</th>
                  {hasBranches && <th>Filial</th>}
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
                        <span className="cell-main" style={{ fontWeight: 500 }}>
                          {ticket.first_name} {ticket.last_name}
                        </span>{' '}
                        {ticket.source === 'seed' && <span className="badge dim">sinov</span>}
                        {ticket.source === 'staff' && <span className="badge blue">xodim qo‘shgan</span>}
                      </td>
                      {hasBranches && <td className="muted">{ticket.branch_name ?? '—'}</td>}
                      <td className="muted">{prettyPhone(ticket.phone)}</td>
                      <td className="muted">{formatDateTime(ticket.registered_at)}</td>
                      <td>
                        <span className={`badge ${label.tone}`}>{label.text}</span>{' '}
                        {ticket.late && <span className="badge amber">kun oxiri</span>}{' '}
                        {ticket.status === 'done' && ticket.contract_signed === true && (
                          <span className="badge teal">shartnoma</span>
                        )}
                        {ticket.status === 'done' && ticket.contract_signed === false && (
                          <span className="badge dim">shartnomasiz</span>
                        )}
                      </td>
                      <td>
                        <span className="row-actions">
                          {(ticket.status === 'registered' || ticket.status === 'skipped') && (
                            <button className="btn ghost sm" onClick={() => checkin.mutate(ticket.number)}>
                              Keldi
                            </button>
                          )}
                          {!['done', 'cancelled'].includes(ticket.status) && (
                            <button
                              className="btn danger-ghost sm"
                              onClick={async () => {
                                if (
                                  await confirm({
                                    title: `№${ticket.number} bekor qilinsinmi?`,
                                    description: `${ticket.first_name} ${ticket.last_name} navbatdan chiqariladi va botda xabar oladi.`,
                                    confirmLabel: 'Bekor qilish',
                                  })
                                )
                                  cancelTicket.mutate(ticket.number)
                              }}
                            >
                              Bekor
                            </button>
                          )}
                        </span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          <div className="stack-list only-mobile">
            {ticketsQuery.data.map((ticket) => {
              const label = STATUS_LABEL[ticket.status]
              return (
                <div className="stack-item" key={ticket.id}>
                  <span className="top">
                    <span style={{ minWidth: 0 }}>
                      <span className="cell-main">
                        <span className="mono">{ticket.number}</span> · {ticket.first_name}{' '}
                        {ticket.last_name}
                      </span>
                      <span className="cell-sub">
                        {prettyPhone(ticket.phone)} · {formatDateTime(ticket.registered_at)}
                        {hasBranches && ticket.branch_name ? ` · ${ticket.branch_name}` : ''}
                      </span>
                    </span>
                    <span style={{ display: 'inline-flex', gap: 6, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                      <span className={`badge ${label.tone}`}>{label.text}</span>
                      {ticket.late && <span className="badge amber">kun oxiri</span>}
                      {ticket.status === 'done' && ticket.contract_signed === true && (
                        <span className="badge teal">shartnoma</span>
                      )}
                      {ticket.status === 'done' && ticket.contract_signed === false && (
                        <span className="badge dim">shartnomasiz</span>
                      )}
                    </span>
                  </span>
                  {!['done', 'cancelled'].includes(ticket.status) && (
                    <span className="foot" style={{ justifyContent: 'flex-start' }}>
                      {(ticket.status === 'registered' || ticket.status === 'skipped') && (
                        <button className="btn ghost sm" onClick={() => checkin.mutate(ticket.number)}>
                          Keldi
                        </button>
                      )}
                      {!['done', 'cancelled'].includes(ticket.status) && (
                        <button
                          className="btn danger-ghost sm"
                          onClick={async () => {
                            if (
                              await confirm({
                                title: `№${ticket.number} bekor qilinsinmi?`,
                                description: `${ticket.first_name} ${ticket.last_name} navbatdan chiqariladi va botda xabar oladi.`,
                                confirmLabel: 'Bekor qilish',
                              })
                            )
                              cancelTicket.mutate(ticket.number)
                          }}
                        >
                          Bekor
                        </button>
                      )}
                    </span>
                  )}
                </div>
              )
            })}
          </div>
          </>
        )}
      </div>

      {addingWalkin && (
        <WalkinModal
          eventId={Number(eventId)}
          branches={event.branches}
          onClose={() => setAddingWalkin(false)}
          onAdded={() => queryClient.invalidateQueries({ queryKey: ['tickets', eventId] })}
        />
      )}
    </>
  )
}
