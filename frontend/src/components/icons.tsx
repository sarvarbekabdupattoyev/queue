/** Inline SVG icon set — 24×24 viewBox, stroke-based, inherits currentColor.
 * UI chrome uses these exclusively (no emoji — see frontend/CLAUDE.md). */

import type { SVGProps } from 'react'

export interface IconProps extends SVGProps<SVGSVGElement> {
  size?: number
}

function make(name: string, children: React.ReactNode) {
  function Icon({ size = 18, ...props }: IconProps) {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.8}
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
        {...props}
      >
        {children}
      </svg>
    )
  }
  Icon.displayName = `Icon${name}`
  return Icon
}

export const IconDashboard = make('Dashboard', (
  <>
    <rect x="3.5" y="3.5" width="7" height="7" rx="2" />
    <rect x="13.5" y="3.5" width="7" height="7" rx="2" />
    <rect x="3.5" y="13.5" width="7" height="7" rx="2" />
    <rect x="13.5" y="13.5" width="7" height="7" rx="2" />
  </>
))

export const IconCalendar = make('Calendar', (
  <>
    <rect x="3.5" y="5" width="17" height="15.5" rx="2.5" />
    <path d="M3.5 10h17M8 2.8v4M16 2.8v4" />
  </>
))

export const IconUsers = make('Users', (
  <>
    <circle cx="9" cy="8" r="3.4" />
    <path d="M3.2 20c.6-3.4 3-5.2 5.8-5.2s5.2 1.8 5.8 5.2" />
    <path d="M15.4 5.2a3.4 3.4 0 0 1 0 5.6M17.8 14.9c1.9.7 3 2.4 3.4 4.6" />
  </>
))

export const IconDesk = make('Desk', (
  <>
    <path d="M3 8.5h18" />
    <path d="M5 8.5V19M19 8.5V19" />
    <path d="M5 13h14" />
  </>
))

export const IconSettings = make('Settings', (
  <>
    <path d="M4 7.5h9M17.5 7.5H20M4 16.5h2.5M11 16.5h9" />
    <circle cx="15" cy="7.5" r="2.3" />
    <circle cx="8.5" cy="16.5" r="2.3" />
  </>
))

export const IconLogout = make('Logout', (
  <>
    <path d="M14 4.5H7a2.5 2.5 0 0 0-2.5 2.5v10A2.5 2.5 0 0 0 7 19.5h7" />
    <path d="M16 8l4 4-4 4M20 12H9.5" />
  </>
))

export const IconScan = make('Scan', (
  <>
    <path d="M4 8V6a2 2 0 0 1 2-2h2M16 4h2a2 2 0 0 1 2 2v2M20 16v2a2 2 0 0 1-2 2h-2M8 20H6a2 2 0 0 1-2-2v-2" />
    <path d="M4 12h16" />
  </>
))

export const IconMonitor = make('Monitor', (
  <>
    <rect x="3" y="4.5" width="18" height="12.5" rx="2.5" />
    <path d="M9 20.5h6M12 17v3.5" />
  </>
))

export const IconSun = make('Sun', (
  <>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2.8v2M12 19.2v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2.8 12h2M19.2 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
  </>
))

export const IconMoon = make('Moon', (
  <path d="M20.5 14.2A8.5 8.5 0 1 1 9.8 3.5a7 7 0 0 0 10.7 10.7z" />
))

export const IconLaptop = make('Laptop', (
  <>
    <rect x="4.5" y="5" width="15" height="10.5" rx="2" />
    <path d="M2.5 19h19" />
  </>
))

export const IconCopy = make('Copy', (
  <>
    <rect x="9" y="9" width="11.5" height="11.5" rx="2.5" />
    <path d="M5.5 15H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v.5" />
  </>
))

export const IconPlus = make('Plus', <path d="M12 5v14M5 12h14" />)

export const IconTrash = make('Trash', (
  <>
    <path d="M4 6.5h16M9.5 3.5h5M6 6.5l.8 12A2 2 0 0 0 8.8 20.5h6.4a2 2 0 0 0 2-1.9l.8-12.1" />
    <path d="M10 10.5v6M14 10.5v6" />
  </>
))

export const IconEdit = make('Edit', (
  <>
    <path d="M12 20h8" />
    <path d="M16.6 3.9a2.1 2.1 0 0 1 3 3L8.4 18.1 4 19.5l1.4-4.4L16.6 3.9z" />
  </>
))

export const IconCheck = make('Check', <path d="M4.5 12.5l5 5 10-11" />)

export const IconX = make('X', <path d="M6 6l12 12M18 6L6 18" />)

export const IconCheckCircle = make('CheckCircle', (
  <>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M8.5 12.4l2.4 2.4 4.6-5" />
  </>
))

export const IconPhone = make('Phone', (
  <path d="M7.6 3.5H5.2A1.8 1.8 0 0 0 3.4 5.4 16.8 16.8 0 0 0 18.6 20.6a1.8 1.8 0 0 0 1.9-1.8v-2.4a1.5 1.5 0 0 0-1.1-1.5l-2.9-.8a1.5 1.5 0 0 0-1.6.6l-.7 1a12.4 12.4 0 0 1-4.9-4.9l1-.7a1.5 1.5 0 0 0 .6-1.6l-.8-2.9a1.5 1.5 0 0 0-1.5-1.1z" />
))

export const IconClock = make('Clock', (
  <>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 7v5.2l3.4 2" />
  </>
))

export const IconSearch = make('Search', (
  <>
    <circle cx="11" cy="11" r="6.5" />
    <path d="M20 20l-4.4-4.4" />
  </>
))

export const IconExternal = make('External', (
  <>
    <path d="M13.5 4.5H19.5V10.5" />
    <path d="M19.5 4.5L11 13" />
    <path d="M19.5 14v3.5a2 2 0 0 1-2 2h-11a2 2 0 0 1-2-2v-11a2 2 0 0 1 2-2H10" />
  </>
))

export const IconCamera = make('Camera', (
  <>
    <path d="M3.5 8.5A2.5 2.5 0 0 1 6 6h1.6l1.5-2.2h5.8L16.4 6H18a2.5 2.5 0 0 1 2.5 2.5v8A2.5 2.5 0 0 1 18 19H6a2.5 2.5 0 0 1-2.5-2.5v-8z" />
    <circle cx="12" cy="12.2" r="3.4" />
  </>
))

export const IconBell = make('Bell', (
  <>
    <path d="M18 10a6 6 0 1 0-12 0c0 4.5-1.8 5.8-1.8 5.8h15.6S18 14.5 18 10z" />
    <path d="M10 19.5a2.2 2.2 0 0 0 4 0" />
  </>
))

export const IconMegaphone = make('Megaphone', (
  <>
    <path d="M3.5 10.5v3a1.5 1.5 0 0 0 1.5 1.5h2l7.5 4.5v-15L7 9H5a1.5 1.5 0 0 0-1.5 1.5z" />
    <path d="M18 9.5a3.5 3.5 0 0 1 0 5" />
  </>
))

export const IconRefresh = make('Refresh', (
  <>
    <path d="M20 5.5v5h-5" />
    <path d="M4 18.5v-5h5" />
    <path d="M5.5 9.5a7 7 0 0 1 12-2.4L20 10.5M4 13.5l2.5 3.4a7 7 0 0 0 12-2.4" />
  </>
))

export const IconSkip = make('Skip', (
  <>
    <path d="M5 5.5l7 6.5-7 6.5zM13.5 5.5l7 6.5-7 6.5z" />
  </>
))

export const IconFlag = make('Flag', (
  <>
    <path d="M5.5 21V4" />
    <path d="M5.5 4.5c4.5-2.5 8.5 2.5 13 0v9c-4.5 2.5-8.5-2.5-13 0" />
  </>
))

export const IconChevronRight = make('ChevronRight', <path d="M9 5.5l6.5 6.5L9 18.5" />)

export const IconSound = make('Sound', (
  <>
    <path d="M4 9.5v5h3.5L12 18.5v-13L7.5 9.5H4z" />
    <path d="M15.5 9a4.2 4.2 0 0 1 0 6M18 6.5a8 8 0 0 1 0 11" />
  </>
))

export const IconExpand = make('Expand', (
  <>
    <path d="M9 4.5H4.5V9M15 4.5h4.5V9M9 19.5H4.5V15M15 19.5h4.5V15" />
  </>
))

export const IconQr = make('Qr', (
  <>
    <rect x="3.5" y="3.5" width="7" height="7" rx="1.5" />
    <rect x="13.5" y="3.5" width="7" height="7" rx="1.5" />
    <rect x="3.5" y="13.5" width="7" height="7" rx="1.5" />
    <path d="M13.5 13.5h3v3h-3zM17.5 17.5h3v3h-3z" />
  </>
))

export const IconBuilding = make('Building', (
  <>
    <rect x="5" y="3.5" width="14" height="17" rx="2" />
    <path d="M9 7.5h2M13 7.5h2M9 11.5h2M13 11.5h2M9 15.5h2M13 15.5h2M12 20.5v-3" />
  </>
))

export const IconMapPin = make('MapPin', (
  <>
    <path d="M12 21s7-5.5 7-11a7 7 0 1 0-14 0c0 5.5 7 11 7 11z" />
    <circle cx="12" cy="10" r="2.6" />
  </>
))

export const IconBot = make('Bot', (
  <>
    <rect x="4.5" y="8" width="15" height="10.5" rx="3" />
    <path d="M12 8V4.5M12 4.5a1.3 1.3 0 1 0-.01 0z" />
    <path d="M9 13.4h.01M15 13.4h.01" strokeWidth={2.6} />
  </>
))

export const IconChart = make('Chart', (
  <>
    <path d="M4 4.5v13a2.5 2.5 0 0 0 2.5 2.5H20" />
    <rect x="7.5" y="11.5" width="3.4" height="5.5" rx="1.2" />
    <rect x="12.5" y="7.5" width="3.4" height="9.5" rx="1.2" />
    <rect x="17.5" y="4.5" width="3.4" height="12.5" rx="1.2" />
  </>
))

export const IconMenu = make('Menu', <path d="M4 7h16M4 12h16M4 17h16" />)

export const IconChevronDown = make('ChevronDown', <path d="M6 9.5l6 6 6-6" />)

export const IconUser = make('User', (
  <>
    <circle cx="12" cy="8" r="3.6" />
    <path d="M5 20a7 7 0 0 1 14 0" />
  </>
))

export const IconArrowUpRight = make('ArrowUpRight', <path d="M7 17L17 7M9 7h8v8" />)

/** SmartNavbat logo glyph: three queue dots advancing to the leader. */
export function Logo({ size = 26 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden="true">
      <rect width="32" height="32" rx="16" fill="var(--logo-bg)" />
      <circle cx="8.6" cy="21" r="2.5" fill="var(--logo-dot)" opacity="0.5" />
      <circle cx="15.2" cy="16" r="3.1" fill="var(--logo-dot)" opacity="0.75" />
      <circle cx="22.6" cy="10.4" r="3.9" fill="var(--logo-dot)" />
    </svg>
  )
}

/** Brand wordmark: logo + "SmartNavbat". */
export function Wordmark({ size = 26, stacked = false }: { size?: number; stacked?: boolean }) {
  return (
    <span className={`wordmark${stacked ? ' stacked' : ''}`}>
      <Logo size={size} />
      <span className="wordmark-text">
        Smart<b>Navbat</b>
      </span>
    </span>
  )
}
