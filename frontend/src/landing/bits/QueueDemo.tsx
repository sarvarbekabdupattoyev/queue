import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { useEffect, useState } from 'react'
import { useLang } from '../../i18n'

interface Person {
  id: string
  name: string
  number: string
  regTime: string
  scanned: boolean
}

const PEOPLE: Person[] = [
  { id: 'a', name: 'Aziza', number: 'KRTA', regTime: '09:01', scanned: true },
  { id: 'b', name: 'Bekzod', number: 'WZQN', regTime: '09:14', scanned: false },
  { id: 'c', name: 'Kamola', number: 'DFHM', regTime: '09:32', scanned: true },
  { id: 'd', name: 'Doston', number: 'PXLE', regTime: '10:05', scanned: true },
]

// phase 0: registration order · phase 1: arrival order · phase 2: final queue
const ORDERS: string[][] = [
  ['a', 'b', 'c', 'd'],
  ['d', 'c', 'a', 'b'],
  ['a', 'c', 'd'],
]

/** Animated proof of the core rule: the final queue follows bot registration
 * time among scanned tickets only — arrival order never matters. */
export function QueueDemo() {
  const { t } = useLang()
  const reduced = useReducedMotion()
  const [phase, setPhase] = useState(reduced ? 2 : 0)

  useEffect(() => {
    if (reduced) return
    const id = window.setInterval(() => setPhase((p) => (p + 1) % 3), 2800)
    return () => window.clearInterval(id)
  }, [reduced])

  const order = ORDERS[phase]
  const byId = new Map(PEOPLE.map((p) => [p.id, p]))
  const excluded = phase === 2 ? PEOPLE.filter((p) => !p.scanned) : []

  return (
    <div className="queue-demo">
      <div className="queue-demo-tabs">
        {t.fair.phases.map((label, i) => (
          <button
            key={label}
            type="button"
            className={`queue-demo-tab${phase === i ? ' active' : ''}`}
            onClick={() => setPhase(i)}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="queue-demo-list">
        <AnimatePresence initial={false}>
          {order.map((id, index) => {
            const person = byId.get(id)!
            return (
              <motion.div
                key={id}
                layout
                initial={{ opacity: 0, scale: 0.94 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.9 }}
                transition={{ type: 'spring', stiffness: 320, damping: 30 }}
                className={`queue-demo-row${phase === 2 ? ' final' : ''}`}
              >
                <span className="qd-pos mono">{phase === 2 ? `${index + 1}` : ''}</span>
                <span className="qd-num mono">{person.number}</span>
                <span className="qd-name">{person.name}</span>
                <span className={`badge ${phase === 1 ? 'teal' : 'blue'}`}>
                  {phase === 1 ? t.fair.arrived : `${person.regTime} · ${t.fair.registered}`}
                </span>
              </motion.div>
            )
          })}
          {excluded.map((person) => (
            <motion.div
              key={person.id}
              layout
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="queue-demo-row excluded"
            >
              <span className="qd-pos" />
              <span className="qd-num mono">{person.number}</span>
              <span className="qd-name">{person.name}</span>
              <span className="badge dim">{t.fair.notScanned}</span>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </div>
  )
}
