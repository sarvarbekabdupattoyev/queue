import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Company } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { ThemeToggle } from './ThemeToggle'
import {
  IconBuilding,
  IconCalendar,
  IconDashboard,
  IconDesk,
  IconLogout,
  IconSettings,
  IconUsers,
  Wordmark,
  type IconProps,
} from './icons'

// order mirrors the setup flow: settings → branches → staff → desks → events
const NAV: { to: string; label: string; Icon: (p: IconProps) => JSX.Element; end?: boolean }[] = [
  { to: '/dashboard', label: 'Boshqaruv', Icon: IconDashboard, end: true },
  { to: '/dashboard/settings', label: 'Sozlamalar', Icon: IconSettings },
  { to: '/dashboard/branches', label: 'Filiallar', Icon: IconBuilding },
  { to: '/dashboard/employees', label: 'Xodimlar', Icon: IconUsers },
  { to: '/dashboard/desks', label: 'Stollar', Icon: IconDesk },
  { to: '/dashboard/events', label: 'Tadbirlar', Icon: IconCalendar },
]

export function useCompany() {
  return useQuery({ queryKey: ['company'], queryFn: () => api<Company>('/company') })
}

export function DashboardLayout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth()
  const { data: company } = useCompany()
  const initials = (user?.first_name?.[0] ?? '') + (user?.last_name?.[0] ?? '')
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Wordmark size={28} />
        <div className="side-label">Menyu</div>
        {NAV.map(({ to, label, Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) => `side-link${isActive ? ' active' : ''}`}
          >
            <Icon size={17} />
            {label}
          </NavLink>
        ))}
        <div className="side-footer">
          <div className="user-chip">
            <span className="avatar">{initials.toUpperCase() || 'S'}</span>
            <span className="who">
              <b>
                {user?.first_name} {user?.last_name}
              </b>
              <span>{company?.name}</span>
            </span>
          </div>
          <div className="side-actions">
            <ThemeToggle />
            <button className="icon-btn" title="Chiqish" aria-label="Chiqish" onClick={logout}>
              <IconLogout size={16} />
            </button>
          </div>
        </div>
      </aside>
      <main className="main">{children}</main>
    </div>
  )
}
