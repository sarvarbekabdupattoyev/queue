import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { uz } from './uz'

export type Lang = 'uz' | 'en' | 'ru'
export type Dict = typeof uz

const STORAGE_KEY = 'sn_lang'
export const LANGS: Lang[] = ['uz', 'en', 'ru']

interface LangContextValue {
  lang: Lang
  setLang: (lang: Lang) => void
  t: Dict
}

const LangContext = createContext<LangContextValue | null>(null)

function readStoredLang(): Lang {
  const stored = localStorage.getItem(STORAGE_KEY)
  return stored === 'uz' || stored === 'en' || stored === 'ru' ? stored : 'uz'
}

// en/ru import Dict from this module; dynamic import keeps the cycle harmless
// at runtime while types stay strict.
import { en } from './en'
import { ru } from './ru'

const DICTS: Record<Lang, Dict> = { uz, en, ru }

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(readStoredLang)

  useEffect(() => {
    document.documentElement.lang = lang
  }, [lang])

  const setLang = useCallback((next: Lang) => {
    setLangState(next)
    localStorage.setItem(STORAGE_KEY, next)
  }, [])

  const value = useMemo(() => ({ lang, setLang, t: DICTS[lang] }), [lang, setLang])
  return <LangContext.Provider value={value}>{children}</LangContext.Provider>
}

export function useLang(): LangContextValue {
  const ctx = useContext(LangContext)
  if (!ctx) throw new Error('useLang must be used inside LangProvider')
  return ctx
}

export function LangSwitcher({ compact = false }: { compact?: boolean }) {
  const { lang, setLang } = useLang()
  return (
    <div className="seg" role="group" aria-label="Language">
      {LANGS.map((code) => (
        <button
          key={code}
          type="button"
          className={`lang-btn${lang === code ? ' active' : ''}`}
          aria-pressed={lang === code}
          onClick={() => setLang(code)}
          style={compact ? undefined : { width: 36 }}
        >
          {code.toUpperCase()}
        </button>
      ))}
    </div>
  )
}
