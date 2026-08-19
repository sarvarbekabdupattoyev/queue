import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { useEffect, useState } from 'react'
import { Logo } from '../../components/icons'
import { useLang } from '../../i18n'

const CALLS = [
  { number: 'KRTA', desk: 3 },
  { number: 'DFHM', desk: 1 },
  { number: 'PXLE', desk: 2 },
]
const NEXT = ['WZQN', 'BJSU', 'MVGO', 'QYCD']

/** Hero product mock: a live TV board, a client ticket and a bot chip,
 * gently floating; the called code cycles. */
export function LiveBoardMock() {
  const { t } = useLang()
  const reduced = useReducedMotion()
  const [index, setIndex] = useState(0)

  useEffect(() => {
    if (reduced) return
    const id = window.setInterval(() => setIndex((i) => (i + 1) % CALLS.length), 3200)
    return () => window.clearInterval(id)
  }, [reduced])

  const call = CALLS[index]
  const float = (delay: number, distance = 7) =>
    reduced
      ? {}
      : {
          animate: { y: [0, -distance, 0] },
          transition: { duration: 5.4, delay, repeat: Infinity, ease: 'easeInOut' as const },
        }

  return (
    <div className="board-mock-wrap" aria-hidden="true">
      <motion.div className="board-mock" {...float(0, 5)}>
        <div className="board-mock-head">
          <span className="live-dot" />
          <span className="board-mock-live">{t.board.live}</span>
          <span className="board-mock-clock mono">09:42</span>
        </div>
        <div className="board-mock-label">{t.board.calling}</div>
        <div className="board-mock-call">
          <AnimatePresence mode="popLayout" initial={false}>
            <motion.span
              key={call.number}
              className="board-mock-number mono"
              initial={reduced ? false : { opacity: 0, y: 22, filter: 'blur(6px)' }}
              animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
              exit={reduced ? undefined : { opacity: 0, y: -22, filter: 'blur(6px)' }}
              transition={{ duration: 0.45, ease: [0.21, 0.6, 0.35, 1] }}
            >
              {call.number}
            </motion.span>
          </AnimatePresence>
          <span className="board-mock-desk">
            {t.board.desk.replace('{n}', String(call.desk))}
          </span>
        </div>
        <div className="board-mock-label">{t.board.next}</div>
        <div className="board-mock-next">
          {NEXT.map((n) => (
            <span key={n} className="mono">
              {n}
            </span>
          ))}
        </div>
      </motion.div>

      <motion.div className="ticket-mock" {...float(1.2, 9)}>
        <div className="ticket-mock-label">{t.board.ticket}</div>
        <div className="ticket-mock-number mono">№KRTA</div>
        <div className="ticket-mock-qr">
          {QR_CELLS.map((on, i) => (
            <span key={i} className={on ? 'on' : ''} />
          ))}
        </div>
        <div className="ticket-mock-until">{t.board.scanUntil}</div>
      </motion.div>

      <motion.div className="bot-chip" {...float(2.1, 6)}>
        <Logo size={18} />
        <span>{t.board.botChip}</span>
      </motion.div>
    </div>
  )
}

// deterministic 11×11 pseudo-QR pattern: solid finder squares + stable noise
const QR_CELLS: boolean[] = (() => {
  const size = 11
  const cells: boolean[] = []
  let seed = 7
  for (let r = 0; r < size; r++) {
    for (let c = 0; c < size; c++) {
      const finder =
        (r < 3 && c < 3) || (r < 3 && c >= size - 3) || (r >= size - 3 && c < 3)
      if (finder) {
        cells.push(true)
      } else {
        seed = (seed * 137 + r * 31 + c * 17) % 97
        cells.push(seed % 5 < 3)
      }
    }
  }
  return cells
})()
