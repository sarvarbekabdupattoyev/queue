import { useQuery } from '@tanstack/react-query'
import { useEffect, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { SaleEvent } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { ThemeToggle } from './ThemeToggle'
import { IconCalendar, IconLogout, Wordmark } from './icons'
import { EmptyState } from './ui'

/** Header + event picker used by the manager and scanner screens. */
export function StaffShell({
  title,
  subtitle,
  eventId,
  onEventChange,
  extra,
  children,
}: {
  title: string
  subtitle: string
  eventId: number | null
  onEventChange: (id: number) => void
  extra?: ReactNode
  children: (event: SaleEvent | null) => ReactNode
}) {
  const { user, logout } = useAuth()
  const { data: events } = useQuery({
    queryKey: ['events'],
    queryFn: () => api<SaleEvent[]>('/events'),
    refetchInterval: 60000,
  })
  const openEvents = events?.filter((e) => e.is_active) ?? []
  const current = openEvents.find((e) => e.id === eventId) ?? null

  useEffect(() => {
    if (openEvents.length === 0) return
    // covers first load and a stale id saved from a deleted/closed event
    if (eventId === null || !openEvents.some((e) => e.id === eventId)) {
      onEventChange(openEvents[0].id)
    }
  }, [eventId, openEvents, onEventChange])

  return (
    <div className="staff-wrap">
      <header className="page-head">
        <div>
          <div style={{ marginBottom: 10 }}>
            <Wordmark size={24} />
          </div>
          <h1 style={{ fontSize: 20 }}>{title}</h1>
          <div className="sub">{subtitle}</div>
        </div>
        <div className="head-actions">
          {openEvents.length > 0 && (
            <select
              className="input"
              style={{ width: 'auto' }}
              value={eventId ?? ''}
              onChange={(e) => onEventChange(Number(e.target.value))}
              aria-label="Tadbir"
            >
              {openEvents.map((event) => (
                <option key={event.id} value={event.id}>
                  {event.name}
                </option>
              ))}
            </select>
          )}
          {extra}
          <ThemeToggle />
          {user?.role === 'owner' && (
            <Link className="btn ghost sm" to="/dashboard">
              Boshqaruv
            </Link>
          )}
          <button className="icon-btn" title="Chiqish" aria-label="Chiqish" onClick={logout}>
            <IconLogout size={16} />
          </button>
        </div>
      </header>
      {openEvents.length === 0 ? (
        <div className="card">
          <EmptyState icon={IconCalendar}>
            Faol tadbirlar yo‘q. Rahbaringiz tadbir e’lon qilishini kuting.
          </EmptyState>
        </div>
      ) : (
        children(current)
      )}
    </div>
  )
}
