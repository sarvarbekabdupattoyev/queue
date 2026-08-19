import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { Branch, Desk, SaleEvent, User } from '../api/types'
import { useCompany } from '../components/DashboardLayout'
import { IconCheck } from '../components/icons'
import { Spinner } from '../components/ui'
import { formatDateTime } from '../lib/format'
import { PHASE_LABEL } from './EventsPage'

export default function DashboardHome() {
  const { data: company } = useCompany()
  const { data: events, isLoading } = useQuery({
    queryKey: ['events'],
    queryFn: () => api<SaleEvent[]>('/events'),
  })
  const { data: employees } = useQuery({
    queryKey: ['employees'],
    queryFn: () => api<User[]>('/employees'),
  })
  const { data: desks } = useQuery({ queryKey: ['desks'], queryFn: () => api<Desk[]>('/desks') })
  const { data: branches } = useQuery({
    queryKey: ['branches'],
    queryFn: () => api<Branch[]>('/branches'),
  })
  const hasBranches = (branches?.length ?? 0) > 0

  const activeEvents = events?.filter((e) => e.is_active && e.phase !== 'closed') ?? []
  // the intended order: settings → branches (only if the company has several
  // offices) → managers → desks → the first tadbir
  const setupSteps = [
    {
      done: !!company?.has_bot_token,
      label: 'Sozlamalar: kompaniya ma’lumotlari va Telegram bot',
      to: '/dashboard/settings',
      optional: false,
    },
    {
      done: hasBranches,
      label: 'Filiallar qo‘shildi (ixtiyoriy — bir nechta ofis bo‘lsa)',
      to: '/dashboard/branches',
      optional: true,
    },
    {
      done: (employees ?? []).some((e) => e.role === 'manager'),
      label: hasBranches ? 'Har bir filialga menejerlar qo‘shildi' : 'Menejerlar qo‘shildi',
      to: '/dashboard/employees',
      optional: false,
    },
    {
      done: (desks?.length ?? 0) > 0,
      label: hasBranches
        ? 'Filiallarda stollar yaratildi va menejerlar biriktirildi'
        : 'Stollar yaratildi va menejerlar biriktirildi',
      to: '/dashboard/desks',
      optional: false,
    },
    {
      done: (events?.length ?? 0) > 0,
      label: 'Sotuv tadbiri e’lon qilindi',
      to: '/dashboard/events',
      optional: false,
    },
  ]
  const pending = setupSteps.filter((s) => !s.done && !s.optional)

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Boshqaruv</h1>
          <div className="sub">{company?.name}</div>
        </div>
        <Link className="btn" to="/dashboard/events">
          Tadbirlarni boshqarish
        </Link>
      </div>

      {pending.length > 0 && (
        <div className="card">
          <div className="card-title">
            Ishga tayyorlash — tartib bilan ({setupSteps.filter((s) => s.done && !s.optional).length}/
            {setupSteps.filter((s) => !s.optional).length})
          </div>
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
                  {step.optional ? 'Ochish' : 'Bajarish'}
                </Link>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="card">
        <div className="card-title">Faol tadbirlar</div>
        {isLoading ? (
          <Spinner />
        ) : activeEvents.length === 0 ? (
          <div className="empty">
            Faol tadbirlar yo‘q. <Link to="/dashboard/events">Sotuv kunini e’lon qiling</Link>.
          </div>
        ) : (
          activeEvents.map((event) => {
            const phase = PHASE_LABEL[event.phase]
            return (
              <div className="list-row" key={event.id}>
                <span>
                  <Link to={`/dashboard/events/${event.id}`} style={{ fontWeight: 700 }}>
                    {event.name}
                  </Link>{' '}
                  <span className="muted">· {formatDateTime(event.starts_at)}</span>{' '}
                  <span className={`badge ${phase.tone}`}>{phase.text}</span>
                </span>
                <span className="mono">
                  {event.checked_in_count}/{event.ticket_count} kelgan
                </span>
              </div>
            )
          })
        )}
      </div>

      <div className="grid-3">
        {hasBranches && (
          <div className="card">
            <div className="card-title">Filiallar</div>
            <div className="mono" style={{ fontSize: 30 }}>
              {branches?.length ?? '—'}
            </div>
            <Link className="hint" to="/dashboard/branches">
              Boshqarish →
            </Link>
          </div>
        )}
        <div className="card">
          <div className="card-title">Xodimlar</div>
          <div className="mono" style={{ fontSize: 30 }}>
            {employees?.length ?? '—'}
          </div>
          <Link className="hint" to="/dashboard/employees">
            Boshqarish →
          </Link>
        </div>
        <div className="card">
          <div className="card-title">Stollar</div>
          <div className="mono" style={{ fontSize: 30 }}>
            {desks?.length ?? '—'}
          </div>
          <Link className="hint" to="/dashboard/desks">
            Boshqarish →
          </Link>
        </div>
        <div className="card">
          <div className="card-title">Telegram botlar</div>
          <div style={{ fontSize: 15, fontWeight: 600 }}>
            {company && company.bots.length > 0
              ? `${company.bots.length} ta ulangan${company.telegram_bot_username ? ` · @${company.telegram_bot_username}` : ''}`
              : 'Ulanmagan'}
          </div>
          <p className="hint" style={{ margin: '4px 0 0' }}>
            Katta ro‘yxatdan o‘tish kunlari uchun {company?.max_bots ?? 3} tagacha parallel bot
            ulash mumkin.
          </p>
          <Link className="hint" to="/dashboard/settings">
            Sozlash →
          </Link>
        </div>
      </div>
    </>
  )
}
