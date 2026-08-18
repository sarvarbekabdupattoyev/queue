import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth, homeFor } from '../auth/AuthContext'
import { ThemeToggle } from '../components/ThemeToggle'
import {
  IconBell,
  IconBot,
  IconBuilding,
  IconCalendar,
  IconCheck,
  IconChevronRight,
  IconClock,
  IconDesk,
  IconMonitor,
  IconQr,
  IconScan,
  IconUsers,
  Logo,
  Wordmark,
} from '../components/icons'
import { LangSwitcher, useLang } from '../i18n'
import { BlurText } from './bits/BlurText'
import { CountUp } from './bits/CountUp'
import { LiveBoardMock } from './bits/LiveBoardMock'
import { Marquee } from './bits/Marquee'
import { QueueDemo } from './bits/QueueDemo'
import { Reveal } from './bits/Reveal'
import { SpotlightCard } from './bits/SpotlightCard'
import './landing.css'

const HOW_ICONS = [IconBot, IconScan, IconClock, IconBell]
const FEATURE_ICONS = [IconBot, IconQr, IconMonitor, IconDesk, IconUsers, IconBell]
const AUDIENCE_ICONS = [IconBuilding, IconCalendar, IconUsers]

function FaqItem({ q, a }: { q: string; a: string }) {
  const [open, setOpen] = useState(false)
  const reduced = useReducedMotion()
  return (
    <div className={`faq-item${open ? ' open' : ''}`}>
      <button type="button" className="faq-q" aria-expanded={open} onClick={() => setOpen(!open)}>
        {q}
        <IconChevronRight size={16} className="chev" />
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={reduced ? false : { height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={reduced ? undefined : { height: 0, opacity: 0 }}
            transition={{ duration: 0.28, ease: [0.3, 0.7, 0.4, 1] }}
            style={{ overflow: 'hidden' }}
          >
            <div className="faq-a">{a}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

export default function LandingPage() {
  const { t } = useLang()
  const { user } = useAuth()

  return (
    <div className="landing">
      <nav className="landing-nav">
        <div className="landing-container landing-nav-inner">
          <Link to="/" aria-label="SmartNavbat">
            <Wordmark size={26} />
          </Link>
          <div className="landing-nav-links">
            <a href="#how">{t.nav.how}</a>
            <a href="#features">{t.nav.features}</a>
            <a href="#faq">{t.nav.faq}</a>
          </div>
          <div className="landing-nav-actions">
            <LangSwitcher />
            <ThemeToggle />
            {user ? (
              <Link className="btn sm" to={homeFor(user.role)}>
                {t.nav.dashboard}
              </Link>
            ) : (
              <>
                <Link className="btn ghost sm" to="/login">
                  {t.nav.login}
                </Link>
                <Link className="btn sm" to="/register">
                  {t.nav.start}
                </Link>
              </>
            )}
          </div>
        </div>
      </nav>

      {/* ------------------------------------------------------------ hero */}
      <header className="landing-hero">
        <div className="landing-container hero-grid">
          <div>
            <Reveal>
              <span className="hero-badge">
                <span className="live-dot" />
                {t.hero.badge}
              </span>
            </Reveal>
            <h1 className="hero-title">
              <BlurText text={t.hero.title1} />{' '}
              <BlurText text={t.hero.titleAccent} className="grad-text" delay={0.25} />
              {t.hero.title2 && (
                <>
                  {' '}
                  <BlurText text={t.hero.title2} delay={0.45} />
                </>
              )}
            </h1>
            <Reveal delay={0.35}>
              <p className="hero-sub">{t.hero.sub}</p>
            </Reveal>
            <Reveal delay={0.45}>
              <div className="hero-ctas">
                <Link className="btn big" to="/register">
                  {t.hero.ctaPrimary}
                  <IconChevronRight size={16} />
                </Link>
                <a className="btn ghost big" href="#how">
                  {t.hero.ctaSecondary}
                </a>
              </div>
              <div className="hero-note">
                <IconCheck size={15} />
                {t.hero.note}
              </div>
            </Reveal>
          </div>
          <Reveal delay={0.25} y={34}>
            <LiveBoardMock />
          </Reveal>
        </div>
      </header>

      {/* ------------------------------------------------------- audiences */}
      <section className="landing-audience">
        <div className="audience-title">{t.audience.title}</div>
        <Marquee>
          {t.audience.items.map((item, i) => {
            const Icon = AUDIENCE_ICONS[i % AUDIENCE_ICONS.length]
            return (
              <span className="marquee-item" key={item}>
                <Icon size={15} />
                {item}
              </span>
            )
          })}
        </Marquee>
      </section>

      {/* ---------------------------------------------------- how it works */}
      <section className="landing-section" id="how">
        <div className="landing-container">
          <Reveal className="section-head">
            <h2 className="section-title">{t.how.title}</h2>
            <p className="section-sub">{t.how.sub}</p>
          </Reveal>
          <div className="how-grid">
            {t.how.steps.map((step, i) => {
              const Icon = HOW_ICONS[i]
              return (
                <Reveal key={step.title} delay={i * 0.08}>
                  <div className="how-card">
                    <span className="how-icon">
                      <Icon size={20} />
                    </span>
                    <h3>{step.title}</h3>
                    <p>{step.text}</p>
                  </div>
                </Reveal>
              )
            })}
          </div>
        </div>
      </section>

      {/* -------------------------------------------------------- fairness */}
      <section className="landing-section alt">
        <div className="landing-container fair-grid">
          <Reveal>
            <h2 className="section-title">{t.fair.title}</h2>
            <p className="section-sub">{t.fair.sub}</p>
          </Reveal>
          <Reveal delay={0.12}>
            <QueueDemo />
          </Reveal>
        </div>
      </section>

      {/* -------------------------------------------------------- features */}
      <section className="landing-section" id="features">
        <div className="landing-container">
          <Reveal className="section-head center">
            <h2 className="section-title">{t.features.title}</h2>
            <p className="section-sub">{t.features.sub}</p>
          </Reveal>
          <div className="features-grid">
            {t.features.items.map((item, i) => {
              const Icon = FEATURE_ICONS[i]
              return (
                <Reveal key={item.title} delay={(i % 3) * 0.08}>
                  <SpotlightCard>
                    <span className="feature-icon">
                      <Icon size={20} />
                    </span>
                    <h3>{item.title}</h3>
                    <p>{item.text}</p>
                  </SpotlightCard>
                </Reveal>
              )
            })}
          </div>
        </div>
      </section>

      {/* ----------------------------------------------------------- stats */}
      <section className="landing-section" style={{ paddingTop: 0 }}>
        <div className="landing-container stats-band">
          {t.stats.map((stat, i) => (
            <Reveal key={stat.label} delay={i * 0.07}>
              <div className="stat-cell">
                <b>
                  <CountUp to={stat.value} prefix={stat.prefix} suffix={stat.suffix} />
                </b>
                <span>{stat.label}</span>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* ---------------------------------------------------------- launch */}
      <section className="landing-section alt">
        <div className="landing-container">
          <Reveal className="section-head center">
            <h2 className="section-title">{t.launch.title}</h2>
            <p className="section-sub">{t.launch.sub}</p>
          </Reveal>
          <div className="launch-grid">
            {t.launch.steps.map((step, i) => (
              <Reveal key={step.title} delay={i * 0.08}>
                <div className="launch-step">
                  <span className="launch-num">{i + 1}</span>
                  <h3>{step.title}</h3>
                  <p>{step.text}</p>
                </div>
              </Reveal>
            ))}
          </div>
          <Reveal className="section-head center" y={16}>
            <Link className="btn big" to="/register">
              {t.launch.cta}
              <IconChevronRight size={16} />
            </Link>
          </Reveal>
        </div>
      </section>

      {/* ------------------------------------------------------------- faq */}
      <section className="landing-section" id="faq">
        <div className="landing-container">
          <Reveal className="section-head center">
            <h2 className="section-title">{t.faq.title}</h2>
          </Reveal>
          <div className="faq-list">
            {t.faq.items.map((item, i) => (
              <Reveal key={item.q} delay={i * 0.05} y={16}>
                <FaqItem q={item.q} a={item.a} />
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* ------------------------------------------------------------- cta */}
      <section className="landing-section" style={{ paddingTop: 20 }}>
        <div className="landing-container">
          <Reveal>
            <div className="landing-cta">
              <h2>{t.cta.title}</h2>
              <p>{t.cta.sub}</p>
              <div className="hero-ctas">
                <Link className="btn big" to="/register">
                  {t.cta.button}
                </Link>
                <Link className="btn ghost big" to="/login">
                  {t.cta.secondary}
                </Link>
              </div>
            </div>
          </Reveal>
        </div>
      </section>

      {/* ---------------------------------------------------------- footer */}
      <footer className="landing-footer">
        <div className="landing-container">
          <div className="footer-grid">
            <div className="footer-brand">
              <Wordmark size={26} />
              <p>{t.footer.tagline}</p>
            </div>
            <div className="footer-col">
              <b>{t.footer.product}</b>
              <a href="#how">{t.nav.how}</a>
              <a href="#features">{t.nav.features}</a>
              <a href="#faq">{t.nav.faq}</a>
            </div>
            <div className="footer-col">
              <b>{t.footer.account}</b>
              <Link to="/login">{t.nav.login}</Link>
              <Link to="/register">{t.nav.start}</Link>
            </div>
            <div className="footer-col">
              <b>smartnavbat.uz</b>
              <LangSwitcher />
              <ThemeToggle />
            </div>
          </div>
          <div className="footer-meta">
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
              <Logo size={16} /> © {new Date().getFullYear()} SmartNavbat · smartnavbat.uz
            </span>
            <span>{t.footer.rights}</span>
          </div>
        </div>
      </footer>
    </div>
  )
}
