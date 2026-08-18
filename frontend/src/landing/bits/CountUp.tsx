import { animate, useInView, useReducedMotion } from 'motion/react'
import { useEffect, useRef, useState } from 'react'

/** Counts up from 0 when scrolled into view (ReactBits-style CountUp). */
export function CountUp({
  to,
  prefix = '',
  suffix = '',
  duration = 1.6,
}: {
  to: number
  prefix?: string
  suffix?: string
  duration?: number
}) {
  const ref = useRef<HTMLSpanElement>(null)
  const inView = useInView(ref, { once: true, margin: '-40px' })
  const reduced = useReducedMotion()
  const [value, setValue] = useState(0)

  useEffect(() => {
    if (!inView) return
    if (reduced) {
      setValue(to)
      return
    }
    const controls = animate(0, to, {
      duration,
      ease: [0.16, 0.8, 0.3, 1],
      onUpdate: (latest) => setValue(Math.round(latest)),
    })
    return () => controls.stop()
  }, [inView, to, duration, reduced])

  return (
    <span ref={ref} className="mono">
      {prefix}
      {value.toLocaleString('ru-RU')}
      {suffix}
    </span>
  )
}
