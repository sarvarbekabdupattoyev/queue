import { useQuery } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useState } from 'react'
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
} from '../components/icons'
import { useToast } from '../components/ui'
import { formatCountdown, formatLongCountdown } from '../lib/format'
import { useLiveState, useTick } from '../lib/useLiveState'

export default function ManagerPage() {
  const { user } = useAuth()
  const toast = useToast()
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

  const { data: desks } = useQuery({ queryKey: ['desks'], queryFn: () => api<Desk[]>('/desks') })

  // prefer the desk assigned to this manager
  useEffect(() => {
    if (deskId === null && desks?.length) {
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

  const desk = desks?.find((d) => d.id === deskId) ?? null
  const mine = useMemo(
    () => state?.active?.find((t) => t.desk_id === deskId) ?? null,
    [state, deskId],
  )
  const others = state?.active?.filter((t) => t.desk_id !== deskId) ?? []
  const waiting = state?.waiting_list ?? []
  const timeoutMs = (state?.call_timeout_minutes ?? 3) * 60000
  const queueStarted = state ? state.event.phase === 'queue' : false
  const untilQueue = state ? new Date(state.event.checkin_until).getTime() - now : 0

  const act = async (path: string, body: Record<string, unknown>, confirmText?: string) => {
    if (confirmText && !window.confirm(confirmText)) return
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
        <select
          className="input"
          style={{ width: 'auto' }}
          value={deskId ?? ''}
          onChange={(e) => selectDesk(Number(e.target.value))}
        >
          {(desks ?? []).map((d) => (
            <option key={d.id} value={d.id}>
              {d.number}-stol{d.manager_id === user?.id ? ' (mening)' : ''}
            </option>
          ))}
        </select>
      }
    >
      {() => (
        <div className="grid-2" style={{ gridTemplateColumns: '1.2fr 1fr', alignItems: 'start' }}>
          <div>
            <div className="card">
              <div className="card-title">
                <span>Mening stolim</span>
                <span>{desk ? `${desk.number}-stol` : ''}</span>
              </div>
              {!queueStarted && state && (
                <p className="hint" style={{ marginBottom: 12 }}>
                  Navbat hali boshlanmagan — skanerlash tugashiga{' '}
                  <b className="mono" style={{ color: 'var(--amber)' }}>
                    {formatLongCountdown(untilQueue)}
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
              {state && (
                <div className="stat-row" style={{ marginTop: 14 }}>
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
              <span>Navbatda (kelganlar)</span>
              <span>{waiting.length ? `${waiting.length} kishi` : ''}</span>
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
