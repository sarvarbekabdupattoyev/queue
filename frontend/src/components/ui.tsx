import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from 'react'
import { IconCopy, IconTrash, IconX, type IconProps } from './icons'

export function Spinner() {
  return <div className="spinner" aria-label="Yuklanmoqda" />
}

export function Modal({
  title,
  description,
  onClose,
  children,
}: {
  title: string
  description?: string
  onClose: () => void
  children: ReactNode
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title}>
        <div className="modal-head">
          <div>
            <h2>{title}</h2>
            {description && <p>{description}</p>}
          </div>
          <button type="button" className="icon-btn" aria-label="Yopish" onClick={onClose}>
            <IconX size={16} />
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  )
}

export function EmptyState({
  icon: Icon,
  children,
  action,
}: {
  icon?: (props: IconProps) => JSX.Element
  children: ReactNode
  action?: ReactNode
}) {
  return (
    <div className="empty-state">
      {Icon && (
        <span className="halo">
          <Icon size={22} />
        </span>
      )}
      <p>{children}</p>
      {action}
    </div>
  )
}

/** Simple form wrapper that traps submit and surfaces API errors. */
export function ActionForm({
  onSubmit,
  children,
}: {
  onSubmit: () => Promise<void>
  children: (busy: boolean, error: string | null) => ReactNode
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const handle = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await onSubmit()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Xatolik yuz berdi')
    } finally {
      setBusy(false)
    }
  }
  return <form onSubmit={handle}>{children(busy, error)}</form>
}

// --------------------------------------------------------------- confirm ---

interface ConfirmOptions {
  title: string
  description?: string
  confirmLabel?: string
  tone?: 'danger' | 'neutral'
  icon?: (props: IconProps) => JSX.Element
}

const ConfirmContext = createContext<(options: ConfirmOptions) => Promise<boolean>>(() =>
  Promise.resolve(false),
)

/** Styled replacement for window.confirm — resolves true on confirmation. */
export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [current, setCurrent] = useState<
    (ConfirmOptions & { resolve: (ok: boolean) => void }) | null
  >(null)
  const cancelRef = useRef<HTMLButtonElement>(null)

  const confirm = useCallback(
    (options: ConfirmOptions) =>
      new Promise<boolean>((resolve) => setCurrent({ ...options, resolve })),
    [],
  )
  const settle = (ok: boolean) => {
    current?.resolve(ok)
    setCurrent(null)
  }

  useEffect(() => {
    if (!current) return
    cancelRef.current?.focus()
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && settle(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current])

  const tone = current?.tone ?? 'danger'
  const Icon = current?.icon ?? IconTrash
  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {current && (
        <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && settle(false)}>
          <div className="modal" style={{ maxWidth: 384 }} role="dialog" aria-modal="true" aria-label={current.title}>
            <span className={`confirm-icon${tone === 'danger' ? ' danger' : ''}`}>
              <Icon size={18} />
            </span>
            <h2 style={{ fontSize: 23, lineHeight: 1.15 }}>{current.title}</h2>
            {current.description && (
              <p className="hint" style={{ marginTop: 8 }}>
                {current.description}
              </p>
            )}
            <div className="modal-actions" style={{ justifyContent: 'stretch' }}>
              <button
                type="button"
                className={`btn ${tone === 'danger' ? 'coral' : ''}`}
                style={{ flex: 1 }}
                onClick={() => settle(true)}
              >
                {current.confirmLabel ?? 'O‘chirish'}
              </button>
              <button
                ref={cancelRef}
                type="button"
                className="btn ghost"
                style={{ flex: 1 }}
                onClick={() => settle(false)}
              >
                Bekor qilish
              </button>
            </div>
          </div>
        </div>
      )}
    </ConfirmContext.Provider>
  )
}

export function useConfirm() {
  return useContext(ConfirmContext)
}

// ---------------------------------------------------------------- toasts ---

const ToastContext = createContext<(message: string, isError?: boolean) => void>(() => {})

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<{ message: string; err: boolean } | null>(null)
  const timer = useRef<number>()
  const show = useCallback((message: string, isError = false) => {
    setToast({ message, err: isError })
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => setToast(null), 3000)
  }, [])
  return (
    <ToastContext.Provider value={show}>
      {children}
      {toast && <div className={`toast${toast.err ? ' err' : ''}`}>{toast.message}</div>}
    </ToastContext.Provider>
  )
}

export function useToast() {
  return useContext(ToastContext)
}

export function CopyButton({ text, label = 'Nusxalash' }: { text: string; label?: string }) {
  const toast = useToast()
  return (
    <button
      type="button"
      className="btn ghost sm"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text)
          toast('Nusxalandi')
        } catch {
          toast('Nusxalab bo‘lmadi', true)
        }
      }}
    >
      <IconCopy size={14} />
      {label}
    </button>
  )
}
