import { useRef, type ReactNode } from 'react'

/** Card with a cursor-following radial glow (ReactBits-style SpotlightCard). */
export function SpotlightCard({
  children,
  className = '',
}: {
  children: ReactNode
  className?: string
}) {
  const ref = useRef<HTMLDivElement>(null)

  const onMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const el = ref.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    el.style.setProperty('--spot-x', `${e.clientX - rect.left}px`)
    el.style.setProperty('--spot-y', `${e.clientY - rect.top}px`)
  }

  return (
    <div ref={ref} className={`spotlight-card ${className}`} onMouseMove={onMouseMove}>
      {children}
    </div>
  )
}
