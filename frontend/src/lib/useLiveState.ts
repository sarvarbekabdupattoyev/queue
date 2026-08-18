import { useEffect, useRef, useState } from 'react'

/**
 * Live event state over WebSocket with automatic reconnect and a slow
 * HTTP polling fallback so screens survive flaky networks.
 */
export function useLiveState<T>(
  url: string | null,
  fallbackFetch: (() => Promise<T>) | null,
): { state: T | null; connected: boolean } {
  const [state, setState] = useState<T | null>(null)
  const [connected, setConnected] = useState(false)
  const fetchRef = useRef(fallbackFetch)
  fetchRef.current = fallbackFetch

  useEffect(() => {
    if (!url) return
    let ws: WebSocket | null = null
    let closed = false
    let retryDelay = 1000
    let retryTimer: number | undefined

    const connect = () => {
      ws = new WebSocket(url)
      ws.onopen = () => {
        setConnected(true)
        retryDelay = 1000
      }
      ws.onmessage = (event) => {
        try {
          setState(JSON.parse(event.data))
        } catch {
          /* ignore malformed frames */
        }
      }
      ws.onclose = () => {
        setConnected(false)
        if (!closed) {
          retryTimer = window.setTimeout(connect, retryDelay)
          retryDelay = Math.min(retryDelay * 2, 15000)
        }
      }
      ws.onerror = () => ws?.close()
    }
    connect()

    const poll = window.setInterval(async () => {
      const fetcher = fetchRef.current
      if (!fetcher) return
      try {
        setState(await fetcher())
      } catch {
        /* server unreachable; websocket retry will handle it */
      }
    }, 25000)

    return () => {
      closed = true
      window.clearTimeout(retryTimer)
      window.clearInterval(poll)
      ws?.close()
    }
  }, [url])

  return { state, connected }
}

/** Re-render every `ms` — for countdown timers. */
export function useTick(ms = 1000): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), ms)
    return () => window.clearInterval(id)
  }, [ms])
  return now
}
