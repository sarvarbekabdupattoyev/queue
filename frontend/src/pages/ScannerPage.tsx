import jsQR from 'jsqr'
import { useCallback, useEffect, useRef, useState } from 'react'
import { api, getToken, wsUrl } from '../api/client'
import type { CheckinResponse, StaffState } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { StaffShell } from '../components/StaffShell'
import { WalkinModal } from '../components/WalkinModal'
import { IconCamera, IconMapPin, IconPlus } from '../components/icons'
import { formatLongCountdown, formatTime } from '../lib/format'
import { useLiveState, useTick } from '../lib/useLiveState'

interface ScanRecord {
  at: number
  kind: CheckinResponse['kind'] | 'error'
  message: string
  number?: string
  name?: string
  branchId?: number | null
}

function resultTone(kind: ScanRecord['kind']): string {
  if (kind === 'arrived') return 'ok'
  if (kind === 'late') return 'late'
  return 'err'
}

export default function ScannerPage() {
  const { user } = useAuth()
  const now = useTick()
  const [eventId, setEventId] = useState<number | null>(() => {
    const saved = localStorage.getItem('navbat_event')
    return saved ? Number(saved) : null
  })
  const selectEvent = useCallback((id: number) => {
    setEventId(id)
    localStorage.setItem('navbat_event', String(id))
  }, [])

  const [input, setInput] = useState('')
  const [last, setLast] = useState<ScanRecord | null>(null)
  const [history, setHistory] = useState<ScanRecord[]>([])
  const [addingWalkin, setAddingWalkin] = useState(false)
  const [cameraOn, setCameraOn] = useState(false)
  const [cameraError, setCameraError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const videoRef = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const lastCodeRef = useRef<{ code: string; at: number }>({ code: '', at: 0 })
  const busyRef = useRef(false)

  const { state } = useLiveState<StaffState>(
    eventId ? wsUrl(`/ws/staff/${eventId}?token=${getToken()}`) : null,
    eventId ? () => api<StaffState>(`/events/${eventId}/state`) : null,
  )

  const submit = useCallback(
    async (raw: string) => {
      const value = raw.trim()
      if (!value || !eventId || busyRef.current) return
      busyRef.current = true
      try {
        // a bare 4-letter code is the queue number; anything longer is a QR code
        const body = /^[A-Za-z]{4}$/.test(value) ? { number: value.toUpperCase() } : { code: value }
        const result = await api<CheckinResponse>(`/queue/${eventId}/checkin`, { body })
        const record: ScanRecord = {
          at: Date.now(),
          kind: result.kind,
          message: result.message,
          number: result.ticket.number,
          name: `${result.ticket.first_name} ${result.ticket.last_name}`,
          branchId: result.ticket.branch_id,
        }
        setLast(record)
        setHistory((h) => [record, ...h].slice(0, 12))
      } catch (e) {
        const record: ScanRecord = {
          at: Date.now(),
          kind: 'error',
          message: e instanceof Error ? e.message : 'Xatolik',
        }
        setLast(record)
        setHistory((h) => [record, ...h].slice(0, 12))
      } finally {
        busyRef.current = false
        setInput('')
        inputRef.current?.focus()
      }
    },
    [eventId],
  )

  // camera scanning loop (BarcodeDetector-free, pure jsQR)
  useEffect(() => {
    if (!cameraOn) return
    let raf = 0
    let cancelled = false
    const canvas = document.createElement('canvas')
    const context = canvas.getContext('2d', { willReadFrequently: true })

    const tick = () => {
      if (cancelled) return
      const video = videoRef.current
      if (video && context && video.readyState === video.HAVE_ENOUGH_DATA) {
        canvas.width = video.videoWidth
        canvas.height = video.videoHeight
        context.drawImage(video, 0, 0)
        const image = context.getImageData(0, 0, canvas.width, canvas.height)
        const found = jsQR(image.data, image.width, image.height, {
          inversionAttempts: 'dontInvert',
        })
        if (found?.data) {
          const at = Date.now()
          // debounce: same code within 4s is one scan
          if (found.data !== lastCodeRef.current.code || at - lastCodeRef.current.at > 4000) {
            lastCodeRef.current = { code: found.data, at }
            void submit(found.data)
          }
        }
      }
      raf = requestAnimationFrame(tick)
    }

    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: 'environment' } })
      .then((stream) => {
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop())
          return
        }
        streamRef.current = stream
        if (videoRef.current) {
          videoRef.current.srcObject = stream
          void videoRef.current.play()
        }
        raf = requestAnimationFrame(tick)
      })
      .catch(() => {
        setCameraError(
          'Kamera ochilmadi. Kamera faqat HTTPS yoki localhost’da ishlaydi — USB skaner yoki qo‘lda kiritishdan foydalaning.',
        )
        setCameraOn(false)
      })

    return () => {
      cancelled = true
      cancelAnimationFrame(raf)
      streamRef.current?.getTracks().forEach((t) => t.stop())
      streamRef.current = null
    }
  }, [cameraOn, submit])

  const checkinOpen = state
    ? state.event.phase !== 'closed' && state.event.phase !== 'ended'
    : true
  const untilDeadline = state ? new Date(state.event.checkin_until).getTime() - now : 0
  const branchName = (id: number | null | undefined) =>
    id == null ? null : (state?.event.branches.find((b) => b.id === id)?.name ?? null)
  // branch scanners watch their own branch's numbers
  const stats =
    user?.branch_id != null
      ? (state?.by_branch.find((b) => b.id === user.branch_id)?.stats ?? state?.stats)
      : state?.stats

  return (
    <StaffShell
      title="QR skaner"
      subtitle="Qabulxona: mijoz QR ko‘rsatadi yoki kodini aytadi"
      eventId={eventId}
      onEventChange={selectEvent}
    >
      {() => (
        <div className="grid-2" style={{ alignItems: 'start' }}>
          <div>
            {state && (
              <div className="card" style={{ marginBottom: 14 }}>
                {untilDeadline > 0 ? (
                  <p>
                    Skanerlash tugashiga{' '}
                    <b className="mono" style={{ color: 'var(--amber)' }}>
                      {formatLongCountdown(untilDeadline)}
                    </b>{' '}
                    qoldi. Shu vaqtgacha skanerlanganlar asosiy navbatga kiradi.
                  </p>
                ) : (
                  <p>
                    <span className="badge amber">Skanerlash vaqti tugagan</span> — endi
                    belgilanganlar <b>kun oxiri navbatiga</b> qo‘shiladi.
                  </p>
                )}
              </div>
            )}

            <div className="card">
              <div className="card-title">Belgilash</div>
              <form
                onSubmit={(e) => {
                  e.preventDefault()
                  void submit(input)
                }}
              >
                <input
                  ref={inputRef}
                  className="input"
                  style={{ fontSize: 20, padding: '14px 16px' }}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="QR kod (USB skaner) yoki 4 harfli kod"
                  autoFocus
                  disabled={!checkinOpen}
                />
                <button className="btn full big" style={{ marginTop: 10 }} disabled={!checkinOpen}>
                  Belgilash
                </button>
              </form>
              <p className="hint" style={{ marginTop: 10 }}>
                USB QR-skaner klaviatura kabi ishlaydi: kursor maydonda tursin — kod o‘zi kiradi.
              </p>
              <div style={{ marginTop: 12 }}>
                {cameraOn ? (
                  <>
                    <video ref={videoRef} className="scan-video" muted playsInline />
                    <button className="btn ghost full" style={{ marginTop: 8 }} onClick={() => setCameraOn(false)}>
                      Kamerani o‘chirish
                    </button>
                  </>
                ) : (
                  <button className="btn ghost full" onClick={() => { setCameraError(null); setCameraOn(true) }}>
                    <IconCamera size={17} /> Kamera bilan skanerlash
                  </button>
                )}
                {cameraError && <div className="error-text">{cameraError}</div>}
              </div>
              <div style={{ marginTop: 12 }}>
                <button
                  className="btn tonal full"
                  disabled={!checkinOpen || !eventId}
                  onClick={() => setAddingWalkin(true)}
                >
                  <IconPlus size={16} /> Mijoz qo‘shish (Telegramsiz)
                </button>
                <p className="hint" style={{ marginTop: 6 }}>
                  Botsiz kelgan mijoz F.I.Sh. va telefon bilan qo‘shiladi — avtomatik navbat
                  oxiriga tushadi va QR + kod oladi.
                </p>
              </div>
            </div>
          </div>

          <div>
            <div className={`scan-result ${last ? resultTone(last.kind) : ''}`}>
              {last ? (
                <>
                  <div className="big">{last.number ? `№${last.number}` : '—'}</div>
                  {last.name && <div style={{ fontSize: 17, fontWeight: 600 }}>{last.name}</div>}
                  {branchName(last.branchId) && (
                    <div
                      className="muted"
                      style={{ marginTop: 2, display: 'inline-flex', alignItems: 'center', gap: 4 }}
                    >
                      <IconMapPin size={14} /> {branchName(last.branchId)}
                    </div>
                  )}
                  <div style={{ marginTop: 6 }}>{last.message}</div>
                </>
              ) : (
                <div className="muted">Natija shu yerda ko‘rinadi</div>
              )}
            </div>

            <div className="card">
              <div className="card-title">Oxirgi belgilashlar</div>
              {history.length === 0 ? (
                <div className="empty">Hozircha yo‘q</div>
              ) : (
                history.map((record) => (
                  <div className="list-row" key={record.at}>
                    <span>
                      <b>{record.number ?? '—'}</b> {record.name ?? record.message}
                    </span>
                    <span className={`badge ${resultTone(record.kind) === 'ok' ? 'teal' : resultTone(record.kind) === 'late' ? 'amber' : 'coral'}`}>
                      {formatTime(new Date(record.at).toISOString())}
                    </span>
                  </div>
                ))
              )}
            </div>

            {stats && (
              <div className="card">
                {user?.branch_id != null && branchName(user.branch_id) && (
                  <div className="card-title">{branchName(user.branch_id)} filiali</div>
                )}
                <div className="stat-row">
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
                </div>
              </div>
            )}
          </div>

          {addingWalkin && eventId && (
            <WalkinModal
              eventId={eventId}
              branches={state?.event.branches ?? []}
              onClose={() => setAddingWalkin(false)}
            />
          )}
        </div>
      )}
    </StaffShell>
  )
}
