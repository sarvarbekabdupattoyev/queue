import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { Branch, Desk, SaleEvent, StatsOverview, User } from '../api/types'
import { useCompany } from '../components/DashboardLayout'
import { LineChart } from '../components/charts'
import { IconCheck, IconChevronRight } from '../components/icons'
import { useAuth } from '../auth/AuthContext'
import { Spinner } from '../components/ui'
import { formatDateTime } from '../lib/format'
import { PHASE_LABEL } from './EventsPage'

export default function DashboardHome() {
  const { user } = useAuth()
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
  const { data: stats } = useQuery({
    queryKey: ['stats', 14],
    queryFn: () => api<StatsOverview>('/stats/overview?days=14'),
  })

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
  const required = setupSteps.filter((s) => !s.optional)
  const today = stats?.daily[stats.daily.length - 1]

  return (
    <>
      <div className="banner">
        <span className="blobs" aria-hidden="true">
          <i />
          <i />
          <i />
        </span>
        <div>
          <h2>Assalomu alaykum, {user?.first_name}!</h2>
          <p>
            {activeEvents.length > 0
              ? `Bugun ${activeEvents.length} ta faol tadbir · ${today?.registered ?? 0} ta yangi ro‘yxat · ${today?.arrived ?? 0} ta mijoz keldi`
              : pending.length > 0
                ? `Tizim tayyor bo‘lishiga ${pending.length} ta qadam qoldi — quyidagi ro‘yxatdan davom eting.`
                : 'Hammasi tayyor. Yangi sotuv kunini e’lon qilib, botni mijozlarga tarqating.'}
          </p>
        </div>
      </div>

      {pending.length > 0 && (
        <div className="card">
          <div className="card-title">
            Ishga tayyorlash — tartib bilan
            <span className="aux">
              {required.length - pending.length}/{required.length} bajarildi
            </span>
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

      <div className="grid-2" style={{ marginTop: 16 }}>
        <div className="card">
          <div className="card-title">
            So‘nggi 14 kun
            <span className="aux">
              <Link to="/dashboard/stats" style={{ display: 'inline-flex', alignItems: 'center', gap: 3 }}>
                Statistika <IconChevronRight size={13} />
              </Link>
            </span>
          </div>
          <div className="kpi" style={{ marginBottom: 14 }}>
            <div>
              <div className="big">{stats?.totals.registered ?? '—'}</div>
              <div className="delta">ro‘yxatdan o‘tgan mijoz</div>
            </div>
            <div>
              <div className="big">{stats?.totals.arrived ?? '—'}</div>
              <div className="delta">kelgani belgilangan</div>
            </div>
            <div>
              <div className="big">{stats?.totals.served ?? '—'}</div>
              <div className="delta">xizmat yakunlangan</div>
            </div>
            <div>
              <div className="big">{stats?.totals.contracts ?? '—'}</div>
              <div className="delta">shartnoma tuzilgan</div>
            </div>
          </div>
          {stats ? (
            <LineChart
              labels={stats.daily.map((d) => d.label)}
              series={[
                { name: 'Yozilganlar', color: 'var(--pastel-blue2)', values: stats.daily.map((d) => d.registered) },
                { name: 'Kelganlar', color: 'var(--pastel-green2)', values: stats.daily.map((d) => d.arrived) },
              ]}
              height={170}
            />
          ) : (
            <div className="skeleton" style={{ height: 170 }} />
          )}
        </div>

        <div className="card">
          <div className="card-title">
            Faol tadbirlar
            <span className="aux">
              <Link to="/dashboard/events" style={{ display: 'inline-flex', alignItems: 'center', gap: 3 }}>
                Barchasi <IconChevronRight size={13} />
              </Link>
            </span>
          </div>
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
                  <span style={{ minWidth: 0 }}>
                    <Link to={`/dashboard/events/${event.id}`} style={{ fontWeight: 600 }}>
                      {event.name}
                    </Link>
                    {event.branches.map((b) => (
                      <span key={b.id} className="badge dim" style={{ marginLeft: 6 }}>
                        {b.name}
                      </span>
                    ))}
                    <span className="cell-sub">
                      {formatDateTime(event.starts_at)} · <span className={`badge ${phase.tone}`}>{phase.text}</span>
                    </span>
                  </span>
                  <span className="mono" style={{ whiteSpace: 'nowrap' }}>
                    {event.checked_in_count}/{event.ticket_count}
                  </span>
                </div>
              )
            })
          )}
        </div>
      </div>

      <div className="grid-3" style={{ marginTop: 16 }}>
        {hasBranches && (
          <div className="card">
            <div className="stat-label">Filiallar</div>
            <div className="mono" style={{ fontSize: 30 }}>
              {branches?.length ?? '—'}
            </div>
            <Link className="hint" to="/dashboard/branches">
              Boshqarish →
            </Link>
          </div>
        )}
        <div className="card">
          <div className="stat-label">Xodimlar</div>
          <div className="stat-value" style={{ fontSize: 30 }}>{employees?.length ?? '—'}</div>
          <Link className="hint" to="/dashboard/employees">
            Boshqarish →
          </Link>
        </div>
        <div className="card">
          <div className="stat-label">Stollar</div>
          <div className="stat-value" style={{ fontSize: 30 }}>{desks?.length ?? '—'}</div>
          <Link className="hint" to="/dashboard/desks">
            Boshqarish →
          </Link>
        </div>
        <div className="card">
          <div className="stat-label">Telegram botlar</div>
          <div style={{ fontSize: 15, fontWeight: 600, margin: '6px 0 2px' }}>
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
