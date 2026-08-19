import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { Link, NavLink, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Company } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { ThemeToggle } from './ThemeToggle'
import {
  IconBuilding,
  IconCalendar,
  IconChart,
  IconChevronDown,
  IconDashboard,
  IconDesk,
  IconExternal,
  IconLogout,
  IconMegaphone,
  IconMenu,
  IconPlus,
  IconScan,
  IconSettings,
  IconUsers,
  IconX,
  Logo,
  type IconProps,
} from './icons'
import { uzDateLine } from '../lib/format'
import { useConfirm } from './ui'

interface NavEntry {
  to: string
  label: string
  Icon: (p: IconProps) => JSX.Element
  end?: boolean
  external?: boolean
}

const NAV_SECTIONS: { label: string; items: NavEntry[] }[] = [
  {
    label: 'Asosiy',
    items: [
      { to: '/dashboard', label: 'Boshqaruv', Icon: IconDashboard, end: true },
      { to: '/dashboard/events', label: 'Tadbirlar', Icon: IconCalendar },
      { to: '/dashboard/stats', label: 'Statistika', Icon: IconChart },
    ],
  },
  {
    // ordered like the setup flow: sozlamalar → filiallar → xodimlar → stollar
    label: 'Tashkilot',
    items: [
      { to: '/dashboard/settings', label: 'Sozlamalar', Icon: IconSettings },
      { to: '/dashboard/branches', label: 'Filiallar', Icon: IconBuilding },
      { to: '/dashboard/employees', label: 'Xodimlar', Icon: IconUsers },
      { to: '/dashboard/desks', label: 'Stollar', Icon: IconDesk },
    ],
  },
  {
    label: 'Ish o‘rinlari',
    items: [
      { to: '/manager', label: 'Menejer paneli', Icon: IconMegaphone, external: true },
      { to: '/scanner', label: 'QR skaner', Icon: IconScan, external: true },
    ],
  },
]

const NAV_ITEMS = NAV_SECTIONS.flatMap((s) => s.items)

/** Longest matching path wins, so nested routes keep their parent's title. */
function titleFor(pathname: string): string {
  const hit = NAV_ITEMS.filter(
    (item) => pathname === item.to || pathname.startsWith(`${item.to}/`),
  ).sort((a, b) => b.to.length - a.to.length)[0]
  return hit?.label ?? 'Boshqaruv'
}

export function useCompany() {
  return useQuery({ queryKey: ['company'], queryFn: () => api<Company>('/company') })
}

// Pages with dynamic headings (event detail) push their title into the topbar.
const TitleContext = createContext<(title: string | null) => void>(() => {})

export function PageTitle({ title }: { title: string }) {
  const setTitle = useContext(TitleContext)
  useEffect(() => {
    setTitle(title)
    return () => setTitle(null)
  }, [title, setTitle])
  return null
}

function AccountMenu() {
  const { user, logout } = useAuth()
  const { data: company } = useCompany()
  const confirm = useConfirm()
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDown = (e: PointerEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('pointerdown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('pointerdown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const initials = ((user?.first_name?.[0] ?? '') + (user?.last_name?.[0] ?? '')).toUpperCase()
  return (
    <div className="account" ref={rootRef}>
      <button
        type="button"
        className="account-btn"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="avatar">{initials || 'S'}</span>
        <span className="who">
          <b>
            {user?.first_name} {user?.last_name}
          </b>
          <span>{company?.name ?? 'Kompaniya'}</span>
        </span>
        <IconChevronDown size={15} className="chev" />
      </button>
      {open && (
        <div className="account-menu" role="menu">
          <div className="menu-row">
            <span>Mavzu</span>
            <ThemeToggle />
          </div>
          <div className="menu-sep" />
          <Link
            role="menuitem"
            className="menu-item"
            to="/dashboard/settings"
            onClick={() => setOpen(false)}
          >
            <IconSettings size={15} /> Sozlamalar
          </Link>
          <div className="menu-sep" />
          <button
            role="menuitem"
            className="menu-item danger"
            onClick={async () => {
              setOpen(false)
              if (
                await confirm({
                  title: 'Tizimdan chiqasizmi?',
                  description: 'Kirish sahifasiga qaytasiz. Saqlanmagan o‘zgarishlar yo‘qoladi.',
                  confirmLabel: 'Chiqish',
                  tone: 'neutral',
                  icon: IconLogout,
                })
              )
                logout()
            }}
          >
            <IconLogout size={15} /> Chiqish
          </button>
        </div>
      )}
    </div>
  )
}

export function DashboardLayout({ children }: { children: ReactNode }) {
  const location = useLocation()
  const { data: company } = useCompany()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [pageTitle, setPageTitle] = useState<string | null>(null)
  const [lifted, setLifted] = useState(false)

  // the drawer never survives a navigation or a desktop resize
  useEffect(() => setDrawerOpen(false), [location.pathname])
  useEffect(() => {
    document.body.style.overflow = drawerOpen ? 'hidden' : ''
    return () => {
      document.body.style.overflow = ''
    }
  }, [drawerOpen])
  useEffect(() => {
    if (!drawerOpen) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setDrawerOpen(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [drawerOpen])
  useEffect(() => {
    const onScroll = () => setLifted(window.scrollY > 4)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  const heading = pageTitle ?? titleFor(location.pathname)
  return (
    <TitleContext.Provider value={setPageTitle}>
      <div className="shell">
        <aside className={`sidebar${drawerOpen ? ' open' : ''}`} id="sidebar">
          <div className="side-card">
            <div className="side-brand">
              <Link to="/dashboard" aria-label="SmartNavbat" style={{ display: 'inline-flex' }}>
                <Logo size={34} />
              </Link>
              <span className="wordmark-text">SmartNavbat</span>
              <button
                type="button"
                className="close"
                aria-label="Menyuni yopish"
                onClick={() => setDrawerOpen(false)}
              >
                <IconX size={17} />
              </button>
            </div>
            <nav className="side-nav">
              {NAV_SECTIONS.map((section) => (
                <div key={section.label}>
                  <p className="nav-label">{section.label}</p>
                  {section.items.map(({ to, label, Icon, end, external }) => (
                    <NavLink
                      key={to}
                      to={to}
                      end={end}
                      className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
                    >
                      <Icon size={17} />
                      {label}
                      {external && (
                        <>
                          <span className="spacer" />
                          <IconExternal size={13} className="ext" />
                        </>
                      )}
                    </NavLink>
                  ))}
                </div>
              ))}
            </nav>
            <AccountMenu />
          </div>
        </aside>
        <div
          className={`shell-backdrop${drawerOpen ? ' show' : ''}`}
          onClick={() => setDrawerOpen(false)}
          aria-hidden="true"
        />

        <main className="main">
          <header className={`topbar${lifted ? ' lifted' : ''}`}>
            <div className="topbar-row">
              <button
                type="button"
                className="burger"
                aria-label="Menyu"
                aria-controls="sidebar"
                aria-expanded={drawerOpen}
                onClick={() => setDrawerOpen(true)}
              >
                <IconMenu size={18} />
              </button>
              <div className="topbar-title">
                <h1>{heading}</h1>
                <div className="topbar-sub">
                  <IconCalendar size={13} />
                  <span>{uzDateLine()}</span>
                  {company?.name && (
                    <>
                      <span className="sep">|</span>
                      <span>{company.name}</span>
                    </>
                  )}
                </div>
              </div>
              <div className="topbar-actions">
                <Link className="btn" to="/dashboard/events?new=1">
                  <IconPlus size={15} />
                  <span className="hide-sm">Yangi tadbir</span>
                </Link>
              </div>
            </div>
          </header>
          {children}
        </main>
      </div>
    </TitleContext.Provider>
  )
}
