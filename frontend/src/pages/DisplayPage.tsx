import { useEffect, useMemo, useRef, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { wsUrl } from '../api/client'
import { IconExpand } from '../components/icons'
import type { PublicState } from '../api/types'
import { UZ_DAYS, UZ_MONTHS, formatCountdown, formatLongCountdown, formatTimeMs } from '../lib/format'
import { useCallSound } from '../lib/useCallSound'
import { useLiveState, useTick } from '../lib/useLiveState'

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
  const [searchParams] = useSearchParams()
  // ?branch=<id> pins a TV to one branch of a multi-branch event
  const branchParam = Number(searchParams.get('branch')) || null
  const now = useTick()
  const { state, connected } = useLiveState<PublicState>(
    displayCode ? wsUrl(`/ws/display/${displayCode}`) : null,
    displayCode ? () => fetchState(displayCode) : null,
  )
  // the loud announcement clip (shared with the manager panel); always on
  // for the TV board — no operator is there to flip a toggle back on
  const { enabled: soundOn, toggle: toggleSound, play: playCallSound } = useCallSound(true, 'sn_display_sound')
  useEffect(() => {
    if (!soundOn) toggleSound()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  const knownCalls = useRef<Set<string>>(new Set())
  const sawFirstState = useRef(false)
  const [search, setSearch] = useState('')

  // fresh-call detection for pulse + sound
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
    if (!state) return
    // never ring for the calls that were already on screen when the TV loaded
    if (!sawFirstState.current) {
      sawFirstState.current = true
      return
    }
    if (freshKeys.size > 0) playCallSound()
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
  const untilSale = new Date(state.event.sale_starts_at).getTime() - now
  const saleEnded = state.event.phase === 'ended'
  const saleHold = state.event.phase === 'hold'
  const queueRunning = state.event.phase === 'queue' || saleHold || state.event.phase === 'closed'
  // a branch TV shows only its branch's calls, queue and stats
  const branchSection =
    branchParam !== null ? (state.by_branch.find((b) => b.id === branchParam) ?? null) : null
  // a pinned branch that this event does not run in must not silently fall
  // back to announcing every branch on that branch's screen
  const branchMissing = branchParam !== null && branchSection === null
  const branchNames = new Map(state.event.branches.map((b) => [b.id, b.name]))
  const called = state.called
    .filter((c) => branchSection === null || c.branch_id === branchSection.id)
    .slice(0, 6)
  const next = branchSection ? branchSection.next : state.next
  const stats = branchSection ? branchSection.stats : state.stats
  const query = search.trim().toLowerCase()
  const visibleNext = query
    ? next.filter(
        (entry) => entry.number.toLowerCase().includes(query) || entry.name.toLowerCase().includes(query),
      )
    : next

  if (branchMissing) {
    return (
      <div className="display-shell" style={{ placeItems: 'center', display: 'grid' }}>
        <div className="display-empty">
          Bu ekran uchun tanlangan filial tadbirda ishtirok etmayapti.
          <br />
          Boshqaruv panelidan filial ekrani havolasini qayta oling.
        </div>
      </div>
    )
  }

  return (
    <div className="display-shell">
      <header className="display-head">
        <div className="display-brand">
          <div className={`conn-dot${connected ? ' on' : ''}`} title="Ulanish" />
          {state.event.logo_url && <img src={state.event.logo_url} alt="" />}
          <div>
            <h1>{state.event.company_name || state.event.name}</h1>
            <small>
              {state.event.name}
              {branchSection ? ` · ${branchSection.name}` : ''} · Onlayn navbat
            </small>
          </div>
        </div>
        <div className="display-stats-mini">
          <div>
            <b>{stats.registered}</b>
            <span>Yozilgan</span>
          </div>
          <div>
            <b>{stats.arrived}</b>
            <span>Kelgan</span>
          </div>
          <div>
            <b>{stats.waiting}</b>
            <span>Kutmoqda</span>
          </div>
          <div>
            <b>{stats.done}</b>
            <span>Yakunlandi</span>
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
          {saleHold && (
            <div className="hold-banner">
              ⏸ Sotuv vaqtincha to‘xtatib turildi — navbat tez orada davom etadi
            </div>
          )}
          {saleEnded ? (
            <div className="display-empty">
              Sotuv yakunlandi.
              <br />
              Tashrifingiz uchun rahmat!
            </div>
          ) : !queueRunning && untilSale > 0 ? (
            <div className="display-countdown">
              <div className="display-eyebrow" style={{ justifyContent: 'center' }}>
                <span>Sotuv boshlanishiga qoldi</span>
              </div>
              <div className="big">{formatLongCountdown(untilSale)}</div>
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
              Kodingiz chiqishini kuting.
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
                    <div className="who">
                      <div className="n">{call.number}</div>
                      <div className="nm">{call.name}</div>
                    </div>
                    <div className="desk">
                      <b>{call.desk_number}-stol</b>
                      {branchSection === null && call.branch_id !== null && (
                        <span>{branchNames.get(call.branch_id)}</span>
                      )}
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
              <span>Keyingi navbat{branchSection ? ` · ${branchSection.name}` : ''}</span>
              <span className="cnt">{stats.waiting ? `${stats.waiting} kishi` : ''}</span>
            </div>
            {next.length > 0 && (
              <input
                className="display-search"
                style={{ marginBottom: '1.2vh' }}
                type="search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Kod yoki F.I.Sh bo‘yicha qidirish"
                aria-label="Navbatdan qidirish"
              />
            )}
            {next.length === 0 ? (
              <div className="display-empty">
                Navbatda hech kim yo‘q.
                <br />
                Kelganingizni qabulxonada belgilating.
              </div>
            ) : visibleNext.length === 0 ? (
              <div className="display-empty">Hech narsa topilmadi.</div>
            ) : (
              <div className="next-list">
                {visibleNext.map((entry, i) => (
                  <div key={entry.number} className={`q${entry.late ? ' late' : ''}`}>
                    <span className="q-pos">{i + 1}</span>
                    <b>{entry.number}</b>
                    <span className="q-name">{entry.name}</span>
                    <span className="q-time">{formatTimeMs(entry.registered_at)}</span>
                  </div>
                ))}
              </div>
            )}
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
          <button className="btn ghost sm" onClick={toggleFullscreen}>
            <IconExpand size={15} /> To‘liq ekran (F)
          </button>
        </div>
      </footer>
    </div>
  )
}
