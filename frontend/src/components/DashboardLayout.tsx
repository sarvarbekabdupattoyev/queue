import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Company } from '../api/types'
import { useAuth } from '../auth/AuthContext'

const NAV = [
  { to: '/dashboard', label: 'Boshqaruv', icon: '▦', end: true },
  { to: '/dashboard/events', label: 'Tadbirlar', icon: '🗓' },
  { to: '/dashboard/employees', label: 'Xodimlar', icon: '👥' },
  { to: '/dashboard/desks', label: 'Stollar', icon: '🪑' },
  { to: '/dashboard/settings', label: 'Sozlamalar', icon: '⚙' },
]

export function useCompany() {
  return useQuery({ queryKey: ['company'], queryFn: () => api<Company>('/company') })
}

export function DashboardLayout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth()
  const { data: company } = useCompany()
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-mark">
          NAV<span>BAT</span>
        </div>
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) => `side-link${isActive ? ' active' : ''}`}
          >
            <span aria-hidden>{item.icon}</span>
            {item.label}
          </NavLink>
        ))}
        <div className="side-footer">
          <div style={{ fontWeight: 600, color: 'var(--text)' }}>{company?.name}</div>
          <div>
            {user?.first_name} {user?.last_name}
          </div>
          <button className="btn ghost sm" style={{ marginTop: 8 }} onClick={logout}>
            Chiqish
          </button>
        </div>
      </aside>
      <main className="main">{children}</main>
    </div>
  )
}
