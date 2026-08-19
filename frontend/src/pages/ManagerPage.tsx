import { useQuery } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, getToken, wsUrl } from '../api/client'
import type { Desk, StaffState, ActionResponse } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { StaffShell } from '../components/StaffShell'
import {
  IconBell,
  IconCheck,
  IconFlag,
  IconMegaphone,
  IconSkip,
  IconSound,
} from '../components/icons'
import { useConfirm, useToast } from '../components/ui'
import { formatCountdown, formatLongCountdown } from '../lib/format'
import { useCallSound } from '../lib/useCallSound'
import { useLiveState, useTick } from '../lib/useLiveState'

export default function ManagerPage() {
  const { user } = useAuth()
  const toast = useToast()
  const confirm = useConfirm()
  const now = useTick()
  const [eventId, setEventId] = useState<number | null>(() => {
    const saved = localStorage.getItem('navbat_event')
    return saved ? Number(saved) : null
  })
  const [deskId, setDeskId] = useState<number | null>(() => {
    const saved = localStorage.getItem('navbat_desk')
    return saved ? Number(saved) : null
  })
  const [busy, setBusy] = useState(false)

  const { data: allDesks } = useQuery({ queryKey: ['desks'], queryFn: () => api<Desk[]>('/desks') })
  // a branch manager works only with their branch's desks
  const desks = useMemo(
    () =>
      (allDesks ?? []).filter(
        (d) => user?.branch_id == null || d.branch_id === user.branch_id,
      ),
    [allDesks, user],
  )

  // prefer the desk assigned to this manager
  useEffect(() => {
    if (desks.length === 0) return
    if (deskId === null || !desks.some((d) => d.id === deskId)) {
      const mine = desks.find((d) => d.manager_id === user?.id)
      setDeskId((mine ?? desks[0]).id)
    }
  }, [deskId, desks, user])

  const selectEvent = useCallback((id: number) => {
    setEventId(id)
    localStorage.setItem('navbat_event', String(id))
  }, [])
  const selectDesk = (id: number) => {
    setDeskId(id)
    localStorage.setItem('navbat_desk', String(id))
  }

  const { state } = useLiveState<StaffState>(
    eventId ? wsUrl(`/ws/staff/${eventId}?token=${getToken()}`) : null,
    eventId ? () => api<StaffState>(`/events/${eventId}/state`) : null,
  )

  const desk = desks.find((d) => d.id === deskId) ?? null
  const { enabled: soundOn, toggle: toggleSound, play: playCallSound } = useCallSound(true)
  // ring loudly whenever a client is (re)called in this desk's scope — the
  // clip fires on fresh `called_at` stamps, never on the first snapshot
  const knownCallsRef = useRef<Set<string> | null>(null)
  useEffect(() => {
    // switching desks changes the scope — re-baseline instead of ringing
    // for calls that were already active there
    knownCallsRef.current = null
  }, [deskId])
  useEffect(() => {
    if (!state) return
    const scope = (state.event.branches?.length ?? 0) > 0 ? (desk?.branch_id ?? null) : null
    const current = new Set(
      (state.active ?? [])
        .filter((t) => t.status === 'called' && (scope === null || t.branch_id === scope))
        .map((t) => `${t.id}:${t.called_at}`),
    )
    const previous = knownCallsRef.current
    knownCallsRef.current = current
    if (previous === null) return
    for (const key of current) {
      if (!previous.has(key)) {
        playCallSound()
        break
      }
    }
  }, [state, desk, playCallSound])
  const mine = useMemo(
    () => state?.active?.find((t) => t.desk_id === deskId) ?? null,
    [state, deskId],
  )
  // branch events: this desk serves only its own branch's slice of the queue
  const eventHasBranches = (state?.event.branches?.length ?? 0) > 0
  const branchScope = eventHasBranches ? (desk?.branch_id ?? null) : null
  const inScope = (t: { branch_id: number | null }) =>
    branchScope === null || t.branch_id === branchScope
  const others = state?.active?.filter((t) => t.desk_id !== deskId && inScope(t)) ?? []
  const waiting = (state?.waiting_list ?? []).filter(inScope)
  const stats =
    branchScope !== null
      ? (state?.by_branch.find((b) => b.id === branchScope)?.stats ?? state?.stats)
      : state?.stats
  const timeoutMs = (state?.call_timeout_minutes ?? 3) * 60000
  const queueStarted = state ? state.event.phase === 'queue' : false
  const saleHold = state?.event.phase === 'hold'
  const saleEnded = state?.event.phase === 'ended'
  const untilSale = state ? new Date(state.event.sale_starts_at).getTime() - now : 0

  const act = async (path: string, body: Record<string, unknown>, confirmText?: string) => {
    if (confirmText && !(await confirm({ title: confirmText, confirmLabel: 'Ha', icon: IconSkip })))
      return
    setBusy(true)
    try {
      const result = await api<ActionResponse>(`/queue/${eventId}/${path}`, { body })
      toast(result.message)
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Xatolik', true)
    } finally {
      setBusy(false)
    }
  }

  const calledLeft = mine?.called_at ? timeoutMs - (now - new Date(mine.called_at).getTime()) : 0

  return (
    <StaffShell
      title="Menejer paneli"
      subtitle="Chaqirish · Keldi · Kelmadi · Yakunlash"
      eventId={eventId}
      onEventChange={selectEvent}
      extra={
        <>
          <select
            className="input"
            style={{ width: 'auto' }}
            value={deskId ?? ''}
            onChange={(e) => selectDesk(Number(e.target.value))}
            aria-label="Stol"
          >
            {desks.map((d) => (
              <option key={d.id} value={d.id}>
                {d.branch_name ? `${d.branch_name} · ` : ''}
                {d.number}-stol{d.manager_id === user?.id ? ' (mening)' : ''}
              </option>
            ))}
          </select>
          <button
            type="button"
            className={`icon-btn${soundOn ? ' on' : ''}`}
            title={soundOn ? 'Chaqiruv ovozi yoniq' : 'Chaqiruv ovozi o‘chiq'}
            aria-label="Chaqiruv ovozi"
            aria-pressed={soundOn}
            onClick={toggleSound}
          >
            <IconSound size={16} />
          </button>
        </>
      }
    >
      {() => (
        <div className="grid-2 split">
          <div>
            <div className="card">
              <div className="card-title">
                Mening stolim
                <span className="aux">
                  {desk
                    ? `${desk.branch_name ? `${desk.branch_name} · ` : ''}${desk.number}-stol`
                    : ''}
                </span>
              </div>
              {eventHasBranches && desk && desk.branch_id === null && (
                <p className="hint" style={{ marginBottom: 12, color: 'var(--amber)' }}>
                  Bu tadbir filiallarda o‘tkazilmoqda, lekin bu stol filialga biriktirilmagan —
                  chaqirish uchun rahbar stolni filialga biriktirishi kerak.
                </p>
              )}
              {saleHold && (
                <p className="hint" style={{ marginBottom: 12, color: 'var(--amber)' }}>
                  ⏸ Sotuv to‘xtatib turilgan — rahbar davom ettirgach chaqiruv ochiladi.
                </p>
              )}
              {saleEnded && (
                <p className="hint" style={{ marginBottom: 12 }}>
                  Sotuv yakunlangan — chaqiruv yopiq.
                </p>
              )}
              {!queueStarted && !saleHold && !saleEnded && state && (
                <p className="hint" style={{ marginBottom: 12 }}>
                  Sotuv hali boshlanmagan — boshlanishiga{' '}
                  <b className="mono" style={{ color: 'var(--amber)' }}>
                    {formatLongCountdown(untilSale)}
                  </b>{' '}
                  qoldi.
                </p>
              )}
              <div className="current-ticket">
                <div className={`n${mine ? '' : ' empty-n'}`}>{mine ? mine.number : 'Bo‘sh'}</div>
                <div>
                  <div className="who">{mine ? mine.name : 'Hozircha mijoz yo‘q'}</div>
                  <div className="meta">
                    {mine
                      ? `${mine.phone} · ${mine.status === 'serving' ? 'xizmatda' : 'chaqirildi'}${mine.late ? ' · kun oxiri navbati' : ''}`
                      : '«Keyingini chaqirish» — kelganlar orasidan ro‘yxatdan o‘tish vaqti bo‘yicha eng birinchisi chaqiriladi.'}
                  </div>
                  {mine?.status === 'called' && (
                    <div className={`timer${calledLeft < 60000 ? ' low' : ''}`}>
                      {calledLeft > 0
                        ? `⏱ ${formatCountdown(calledLeft)} — kelmasa «Kelmadi» bosing`
                        : '⏱ Vaqt tugadi — «Kelmadi» bosishingiz mumkin'}
                    </div>
                  )}
                </div>
              </div>
              <div className="btn-grid">
                <button
                  className="btn big span2"
                  disabled={busy || !!mine || !deskId || !queueStarted}
                  onClick={() => act('call', { desk_id: deskId })}
                >
                  <IconMegaphone size={19} /> Keyingini chaqirish
                </button>
                <button
                  className="btn teal big"
                  disabled={busy || mine?.status !== 'called'}
                  onClick={() => mine && act('serving', { number: mine.number })}
                >
                  <IconCheck size={18} /> Keldi
                </button>
                <button
                  className="btn coral big"
                  disabled={busy || mine?.status !== 'called'}
                  onClick={() =>
                    mine && act('skip', { number: mine.number }, `№${mine.number} kelmadi — o‘tkazib yuborilsinmi?`)
                  }
                >
                  <IconSkip size={18} /> Kelmadi
                </button>
                <button
                  className="btn ghost big"
                  disabled={busy || mine?.status !== 'called'}
                  onClick={() => mine && act('recall', { number: mine.number })}
                >
                  <IconBell size={18} /> Takror chaqirish
                </button>
                <button
                  className="btn amber big"
                  disabled={busy || !mine}
                  onClick={() => mine && act('done', { number: mine.number })}
                >
                  <IconFlag size={18} /> Yakunlash
                </button>
              </div>
              {stats && (
                <div className="stat-row" style={{ marginTop: 14 }}>
                  <div className="stat">
                    <b>{stats.registered}</b>
                    <span>Yozilgan</span>
                  </div>
                  <div className="stat">
                    <b>{stats.arrived}</b>
                    <span>Kelgan</span>
                  </div>
                  <div className="stat">
                    <b>{stats.waiting}</b>
                    <span>Kutmoqda</span>
                  </div>
                  <div className="stat">
                    <b>{stats.done}</b>
                    <span>Yakunlandi</span>
                  </div>
                </div>
              )}
            </div>

            <div className="card">
              <div className="card-title">Boshqa stollar</div>
              {others.length === 0 ? (
                <div className="empty">—</div>
              ) : (
                others.map((t) => (
                  <div className="list-row" key={t.id}>
                    <span>
                      <b>{t.number}</b> {t.name}
                    </span>
                    <span className="muted">
                      {t.desk_number}-stol · {t.status === 'serving' ? 'xizmatda' : 'chaqirildi'}
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="card">
            <div className="card-title">
              Navbatda (kelganlar
              {branchScope !== null && desk?.branch_name ? ` · ${desk.branch_name}` : ''})
              <span className="aux">{waiting.length ? `${waiting.length} kishi` : ''}</span>
            </div>
            {waiting.length === 0 ? (
              <div className="empty">
                Hozircha hech kim yo‘q — mijozlar qabulxonada QR skanerlatishi kerak
              </div>
            ) : (
              waiting.slice(0, 30).map((t, i) => (
                <div className="list-row" key={t.id}>
                  <span>
                    <b>{t.number}</b> {t.name}
                    {t.late && <span className="badge amber"> kun oxiri</span>}
                  </span>
                  <span className="muted">{i === 0 ? 'keyingi' : ''}</span>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </StaffShell>
  )
}
