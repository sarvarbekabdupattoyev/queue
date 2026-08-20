import type { ReactNode } from 'react'

// With only 2 copies, any viewport wider than one copy's content scrolls
// past the last copy before the loop resets, exposing blank space that
// reads as the animation ending instead of looping. 4 copies keeps that
// margin comfortable up to very wide desktop viewports.
const COPIES = 4

/** Infinite horizontal loop (ReactBits-style LogoLoop), pure CSS animation. */
export function Marquee({ children, duration = 28 }: { children: ReactNode; duration?: number }) {
  return (
    <div className="marquee" aria-hidden="true">
      <div className="marquee-track" style={{ animationDuration: `${duration}s` }}>
        {Array.from({ length: COPIES }, (_, i) => (
          <div className="marquee-group" key={i}>
            {children}
          </div>
        ))}
      </div>
    </div>
  )
}
