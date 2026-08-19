// All product times are Tashkent local time (UTC+5, no DST) in 24-hour
// format — never the viewer's browser timezone and never AM/PM.
const TASHKENT_OFFSET_MS = 5 * 60 * 60 * 1000

/** A Date whose getUTC* parts read as Tashkent wall-clock time. */
function tashkentClock(iso: string): Date {
  return new Date(new Date(iso).getTime() + TASHKENT_OFFSET_MS)
}

const pad = (n: number) => String(n).padStart(2, '0')

export function formatDateTime(iso: string): string {
  const d = tashkentClock(iso)
  return `${pad(d.getUTCDate())}.${pad(d.getUTCMonth() + 1)}.${d.getUTCFullYear()} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`
}

export function formatTime(iso: string): string {
  const d = tashkentClock(iso)
  return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`
}

/** ISO → {date: "YYYY-MM-DD", time: "HH:MM"} in Tashkent wall-clock time. */
export function isoToTashkentParts(iso: string): { date: string; time: string } {
  const d = tashkentClock(iso)
  return {
    date: `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`,
    time: `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`,
  }
}

/** Tashkent wall-clock date + 24h time → ISO string (UTC). */
export function tashkentPartsToIso(date: string, time: string): string {
  return new Date(`${date}T${time}:00+05:00`).toISOString()
}

export function prettyPhone(phone: string): string {
  const m = phone.match(/^\+998(\d{2})(\d{3})(\d{2})(\d{2})$/)
  if (!m) return phone
  return `+998 ${m[1]} ${m[2]} ${m[3]} ${m[4]}`
}

/** "mm:ss" for a countdown, never negative. */
export function formatCountdown(ms: number): string {
  const total = Math.max(0, Math.ceil(ms / 1000))
  const m = Math.floor(total / 60)
  const s = total % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

/** "1 kun 3:04:05" style countdown for long waits. */
export function formatLongCountdown(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000))
  const days = Math.floor(total / 86400)
  const h = Math.floor((total % 86400) / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const clock = `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return days > 0 ? `${days} kun ${clock}` : clock
}

