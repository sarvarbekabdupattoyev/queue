import { useQuery } from '@tanstack/react-query'
import { useEffect, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { SaleEvent } from '../api/types'
import { useAuth } from '../auth/AuthContext'

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
    <div style={{ maxWidth: 1100, margin: '0 auto', padding: 16 }}>
      <header className="page-head">
        <div>
          <h1 style={{ fontSize: 20 }}>{title}</h1>
          <div className="sub">{subtitle}</div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          {openEvents.length > 0 && (
            <select
              className="input"
              style={{ width: 'auto' }}
              value={eventId ?? ''}
              onChange={(e) => onEventChange(Number(e.target.value))}
            >
              {openEvents.map((event) => (
                <option key={event.id} value={event.id}>
                  {event.name}
                </option>
              ))}
            </select>
          )}
          {extra}
          {user?.role === 'owner' && (
            <Link className="btn ghost sm" to="/dashboard">
              ← Boshqaruv
            </Link>
          )}
          <button className="btn ghost sm" onClick={logout}>
            Chiqish
          </button>
        </div>
      </header>
      {openEvents.length === 0 ? (
        <div className="card">
          <div className="empty">Faol tadbirlar yo‘q. Rahbaringiz tadbir e’lon qilishini kuting.</div>
        </div>
      ) : (
        children(current)
      )}
    </div>
  )
}
