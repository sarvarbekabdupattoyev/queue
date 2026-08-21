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

    let lastFrameAt = 0

    const connect = () => {
      const socket = new WebSocket(url)
      ws = socket
      // Every handler checks that it still belongs to the current socket: a
      // superseded one firing late would otherwise schedule a second retry
      // chain (a reconnect storm on a screen that runs all day) or close the
      // socket that replaced it.
      socket.onopen = () => {
        if (ws !== socket) return
        setConnected(true)
        retryDelay = 1000
      }
      socket.onmessage = (event) => {
        if (ws !== socket) return
        try {
          setState(JSON.parse(event.data))
          lastFrameAt = Date.now()
        } catch {
          /* ignore malformed frames */
        }
      }
      socket.onclose = () => {
        if (ws !== socket) return
        setConnected(false)
        if (!closed) {
          retryTimer = window.setTimeout(connect, retryDelay)
          retryDelay = Math.min(retryDelay * 2, 15000)
        }
      }
      socket.onerror = () => socket.close()
    }
    connect()

    const poll = window.setInterval(async () => {
      const fetcher = fetchRef.current
      if (!fetcher) return
      const startedAt = Date.now()
      try {
        const fetched = await fetcher()
        // a live frame that arrived while this request was in flight is newer
        // than what it returns — don't put the screen back on the older state
        if (lastFrameAt > startedAt) return
        setState(fetched)
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

/**
 * A value that settles `ms` after it stops changing — for search boxes, where
 * the query key would otherwise change on every keystroke and send one
 * full-text request per letter.
 */
export function useDebounced<T>(value: T, ms = 300): T {
  const [settled, setSettled] = useState(value)
  useEffect(() => {
    const id = window.setTimeout(() => setSettled(value), ms)
    return () => window.clearTimeout(id)
  }, [value, ms])
  return settled
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
