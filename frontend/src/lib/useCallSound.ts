import { useCallback, useEffect, useRef, useState } from 'react'
import callSoundUrl from '../assets/call-notification.mp3'

/** Loudness boost applied through WebAudio: a compressor tames the peaks so
 * the extra gain raises perceived volume without harsh clipping. */
const BOOST = 1.6

/**
 * The call-announcement sound (manager panel and TV display). Plays the
 * bundled notification clip at full volume, boosted through a WebAudio
 * compressor+gain chain where available.
 *
 * Browsers only allow sound after one user gesture, so the hook primes the
 * element on the first pointer/key interaction — after that, calls arriving
 * over the WebSocket can ring without any click.
 */
export function useCallSound(defaultOn: boolean, storageKey = 'sn_call_sound') {
  const [enabled, setEnabled] = useState<boolean>(() => {
    try {
      const saved = localStorage.getItem(storageKey)
      return saved === null ? defaultOn : saved === '1'
    } catch {
      return defaultOn
    }
  })
  const enabledRef = useRef(enabled)
  enabledRef.current = enabled
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const contextRef = useRef<AudioContext | null>(null)
  const unlockedRef = useRef(false)

  const element = useCallback(() => {
    if (!audioRef.current) {
      const audio = new Audio(callSoundUrl)
      audio.preload = 'auto'
      audio.volume = 1
      audioRef.current = audio
      try {
        const context = new AudioContext()
        const source = context.createMediaElementSource(audio)
        const compressor = context.createDynamicsCompressor()
        const gain = context.createGain()
        gain.gain.value = BOOST
        source.connect(compressor)
        compressor.connect(gain)
        gain.connect(context.destination)
        contextRef.current = context
      } catch {
        /* WebAudio unavailable — the plain element still plays at volume 1 */
      }
    }
    return audioRef.current
  }, [])

  useEffect(() => {
    const unlock = () => {
      if (unlockedRef.current) return
      unlockedRef.current = true
      const audio = element()
      void contextRef.current?.resume().catch(() => {})
      audio.muted = true
      audio
        .play()
        .then(() => {
          audio.pause()
          audio.currentTime = 0
          audio.muted = false
        })
        .catch(() => {
          audio.muted = false
        })
    }
    window.addEventListener('pointerdown', unlock)
    window.addEventListener('keydown', unlock)
    return () => {
      window.removeEventListener('pointerdown', unlock)
      window.removeEventListener('keydown', unlock)
      // Browsers cap how many AudioContexts a page may hold (~6 in Chrome).
      // A staff screen moving between panels all day would otherwise leave one
      // running per visit and eventually lose sound entirely.
      const context = contextRef.current
      contextRef.current = null
      audioRef.current = null
      unlockedRef.current = false
      void context?.close().catch(() => {})
    }
  }, [element])

  const play = useCallback(() => {
    if (!enabledRef.current) return
    const audio = element()
    void contextRef.current?.resume().catch(() => {})
    audio.currentTime = 0
    audio.volume = 1
    void audio.play().catch(() => {
      /* blocked until the operator touches the page once */
    })
  }, [element])

  const toggle = useCallback(() => {
    const next = !enabledRef.current
    enabledRef.current = next
    try {
      localStorage.setItem(storageKey, next ? '1' : '0')
    } catch {
      /* private mode — the choice just won't persist */
    }
    setEnabled(next)
    if (next) {
      // the toggle tap doubles as the unlock gesture + a volume preview
      const audio = element()
      void contextRef.current?.resume().catch(() => {})
      audio.currentTime = 0
      void audio.play().catch(() => {})
    }
  }, [element, storageKey])

  return { enabled, toggle, play }
}
