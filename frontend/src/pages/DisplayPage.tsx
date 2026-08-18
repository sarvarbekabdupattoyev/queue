import { useEffect, useMemo, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { wsUrl } from '../api/client'
import { IconExpand, IconSound } from '../components/icons'
import type { PublicState } from '../api/types'
import { formatCountdown, formatLongCountdown } from '../lib/format'
import { useLiveState, useTick } from '../lib/useLiveState'

const UZ_MONTHS = ['yanvar', 'fevral', 'mart', 'aprel', 'may', 'iyun', 'iyul', 'avgust', 'sentyabr', 'oktyabr', 'noyabr', 'dekabr']
const UZ_DAYS = ['yakshanba', 'dushanba', 'seshanba', 'chorshanba', 'payshanba', 'juma', 'shanba']

async function fetchState(displayCode: string): Promise<PublicState> {
  const response = await fetch(`/api/public/display/${displayCode}`)
  if (!response.ok) throw new Error('unreachable')
  return response.json()
}

function CountdownRing({ calledAt, timeoutMs, now }: { calledAt: string; timeoutMs: number; now: number }) {
  const left = Math.max(0, timeoutMs - (now - new Date(calledAt).getTime()))
  const frac = timeoutMs > 0 ? left / timeoutMs : 0
  const C = 106.8
  return (
    <div className={`cd${frac < 0.34 ? ' low' : ''}`}>
      <svg viewBox="0 0 40 40">
        <circle className="bg" cx="20" cy="20" r="17" />
        <circle
          className="fg"
          cx="20"
          cy="20"
          r="17"
          strokeDasharray={C}
          strokeDashoffset={C * (1 - frac)}
        />
      </svg>
      <em>{left > 0 ? formatCountdown(left) : 'vaqt tugadi'}</em>
    </div>
  )
}

export default function DisplayPage() {
  const { displayCode } = useParams()
  const now = useTick()
  const { state, connected } = useLiveState<PublicState>(
    displayCode ? wsUrl(`/ws/display/${displayCode}`) : null,
    displayCode ? () => fetchState(displayCode) : null,
  )
  const [soundOn, setSoundOn] = useState(false)
  const knownCalls = useRef<Set<string>>(new Set())
  const audioContext = useRef<AudioContext | null>(null)

  const chime = () => {
    try {
      audioContext.current = audioContext.current ?? new AudioContext()
      const ctx = audioContext.current
      const t0 = ctx.currentTime
      ;[
        [880, 0],
        [660, 0.18],
      ].forEach(([freq, dt]) => {
        const osc = ctx.createOscillator()
        const gain = ctx.createGain()
        osc.type = 'sine'
        osc.frequency.value = freq
        osc.connect(gain)
        gain.connect(ctx.destination)
        gain.gain.setValueAtTime(0.0001, t0 + dt)
        gain.gain.exponentialRampToValueAtTime(0.4, t0 + dt + 0.02)
        gain.gain.exponentialRampToValueAtTime(0.0001, t0 + dt + 0.55)
        osc.start(t0 + dt)
        osc.stop(t0 + dt + 0.6)
      })
    } catch {
      /* audio unavailable */
    }
  }

  // fresh-call detection for pulse + chime
  const freshKeys = useMemo(() => {
    if (!state) return new Set<string>()
    const fresh = new Set<string>()
    for (const call of state.called) {
      const key = `${call.number}:${call.called_at}`
      if (!knownCalls.current.has(key) && call.status === 'called') fresh.add(key)
    }
    knownCalls.current = new Set(state.called.map((c) => `${c.number}:${c.called_at}`))
    return fresh
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state])

  useEffect(() => {
    if (freshKeys.size > 0 && soundOn) chime()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [freshKeys])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'f' || e.key === 'F') toggleFullscreen()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const toggleFullscreen = () => {
    if (document.fullscreenElement) void document.exitFullscreen()
    else void document.documentElement.requestFullscreen()
  }

  const date = new Date(now)
  const clock = `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
  const dateLine = `${date.getDate()}-${UZ_MONTHS[date.getMonth()]}, ${UZ_DAYS[date.getDay()]}`

  if (!state) {
    return (
      <div className="display-shell" style={{ placeItems: 'center', display: 'grid' }}>
        <div className="display-empty">Ekran yuklanmoqda…</div>
      </div>
    )
  }

  const timeoutMs = state.call_timeout_minutes * 60000
  const untilQueue = new Date(state.event.checkin_until).getTime() - now
  const queueRunning = state.event.phase === 'queue' || state.event.phase === 'closed'
  const called = state.called.slice(0, 6)
  const lateSet = new Set(state.late_numbers)

  return (
    <div className="display-shell">
      <header className="display-head">
        <div className="display-brand">
          <div className={`conn-dot${connected ? ' on' : ''}`} title="Ulanish" />
          {state.event.logo_url && <img src={state.event.logo_url} alt="" />}
          <div>
            <h1>{state.event.company_name || state.event.name}</h1>
            <small>{state.event.name} · Onlayn navbat</small>
          </div>
        </div>
        <div className="display-clock">
          <b>{clock}</b>
          <span>{dateLine}</span>
        </div>
      </header>

      <main className="display-main">
        <section className="display-panel">
          <div className="display-eyebrow">
            <span>Hozir chaqirilmoqda</span>
            <span className="cnt">{called.length ? `${called.length} ta stol` : ''}</span>
          </div>
          {!queueRunning && untilQueue > 0 ? (
            <div className="display-countdown">
              <div className="display-eyebrow" style={{ justifyContent: 'center' }}>
                <span>Navbat boshlanishiga qoldi</span>
              </div>
              <div className="big">{formatLongCountdown(untilQueue)}</div>
              <p style={{ marginTop: '2vh', color: 'var(--dsp-dim)', fontSize: 'clamp(13px,2vh,26px)' }}>
                Kelganingizni qabulxonada QR-kod bilan belgilating.
                <br />
                Navbat tartibi — botdan ro‘yxatdan o‘tish vaqti bo‘yicha.
              </p>
            </div>
          ) : called.length === 0 ? (
            <div className="display-empty">
              Hozircha chaqiruv yo‘q.
              <br />
              Raqamingiz chiqishini kuting.
            </div>
          ) : (
            <div className={`tiles${called.length === 1 ? ' one' : ''}`}>
              {called.map((call) => {
                const key = `${call.number}:${call.called_at}`
                const expired =
                  call.status === 'called' &&
                  call.called_at !== null &&
                  now - new Date(call.called_at).getTime() > timeoutMs
                return (
                  <div
                    key={key}
                    className={`tile${call.status === 'serving' ? ' serving' : ''}${freshKeys.has(key) ? ' fresh' : ''}${expired ? ' expired' : ''}`}
                  >
                    <div className="n">{call.number}</div>
                    <div className="desk">
                      <b>{call.desk_number}-stol</b>
                      <span>{call.status === 'serving' ? 'xizmatda' : 'chaqirildi'}</span>
                      {call.status === 'called' && call.called_at && (
                        <CountdownRing calledAt={call.called_at} timeoutMs={timeoutMs} now={now} />
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </section>

        <div className="display-right">
          <section className="display-panel">
            <div className="display-eyebrow">
              <span>Keyingi navbat</span>
              <span className="cnt">{state.stats.waiting ? `${state.stats.waiting} kishi` : ''}</span>
            </div>
            {state.next.length === 0 ? (
              <div className="display-empty">
                Navbatda hech kim yo‘q.
                <br />
                Kelganingizni qabulxonada belgilating.
              </div>
            ) : (
              <div className="next-list">
                {state.next.slice(0, 10).map((n) => (
                  <div key={n} className={`q${lateSet.has(n) ? ' late' : ''}`}>
                    {n}
                  </div>
                ))}
              </div>
            )}
          </section>
          <section className="display-panel" style={{ padding: '1.6vh 1.6vw' }}>
            <div className="display-stats">
              <div className="stat">
                <b>{state.stats.registered}</b>
                <span>Yozilgan</span>
              </div>
              <div className="stat">
                <b>{state.stats.arrived}</b>
                <span>Kelgan</span>
              </div>
              <div className="stat">
                <b>{state.stats.waiting}</b>
                <span>Kutmoqda</span>
              </div>
              <div className="stat">
                <b>{state.stats.done}</b>
                <span>Yakunlandi</span>
              </div>
            </div>
          </section>
        </div>
      </main>

      <footer className="display-foot">
        <div>
          Kelganingizni qabulxonada <b>QR-kod</b> bilan belgilating · Chaqirilgach{' '}
          <b>{state.call_timeout_minutes}</b> daqiqa ichida stolga yaqinlashing · Kechikkanlar kun
          oxirida qabul qilinadi
        </div>
        <div style={{ display: 'flex', gap: '0.6vw' }}>
          <button
            className={`btn ghost sm${soundOn ? ' on' : ''}`}
            onClick={() => {
              setSoundOn((s) => !s)
              if (!soundOn) chime()
            }}
          >
            <IconSound size={15} /> Ovoz
          </button>
          <button className="btn ghost sm" onClick={toggleFullscreen}>
            <IconExpand size={15} /> To‘liq ekran (F)
          </button>
        </div>
      </footer>
    </div>
  )
}
