import type { ReactNode } from 'react'

/** Infinite horizontal loop (ReactBits-style LogoLoop), pure CSS animation. */
export function Marquee({ children, duration = 28 }: { children: ReactNode; duration?: number }) {
  return (
    <div className="marquee" aria-hidden="true">
      <div className="marquee-track" style={{ animationDuration: `${duration}s` }}>
        <div className="marquee-group">{children}</div>
        <div className="marquee-group">{children}</div>
      </div>
    </div>
  )
}
