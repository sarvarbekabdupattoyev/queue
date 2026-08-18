import { motion, useReducedMotion } from 'motion/react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useLang, LangSwitcher } from '../i18n'
import { ThemeToggle } from './ThemeToggle'
import { IconCheck, IconChevronRight, Wordmark } from './icons'
import '../landing/landing.css'

/** Split-screen auth layout: brand story on the left, the form on the right. */
export function AuthShell({ children }: { children: ReactNode }) {
  const { t } = useLang()
  const reduced = useReducedMotion()
  return (
    <div className="auth2">
      <aside className="auth2-brand">
        <Link to="/" aria-label="SmartNavbat">
          <Wordmark size={26} />
        </Link>
        <div className="auth2-brand-body">
          <h2>{t.auth.panelTitle}</h2>
          {t.auth.panelPoints.map((point) => (
            <div className="auth2-point" key={point}>
              <span className="mark">
                <IconCheck size={13} />
              </span>
              {point}
            </div>
          ))}
        </div>
        <div className="auth2-brand-foot">smartnavbat.uz</div>
      </aside>
      <main className="auth2-form-side">
        <div className="auth2-top">
          <Link to="/" className="btn ghost sm" style={{ gap: 4 }}>
            <IconChevronRight size={14} style={{ transform: 'rotate(180deg)' }} />
            {t.auth.backHome}
          </Link>
          <div style={{ display: 'flex', gap: 8 }}>
            <LangSwitcher />
            <ThemeToggle />
          </div>
        </div>
        <motion.div
          className="auth2-card"
          initial={reduced ? false : { opacity: 0, y: 22 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: [0.21, 0.6, 0.35, 1] }}
        >
          {children}
        </motion.div>
      </main>
    </div>
  )
}
