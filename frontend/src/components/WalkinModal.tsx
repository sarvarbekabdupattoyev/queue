import { useState } from 'react'
import { api } from '../api/client'
import type { EventBranch, WalkinResponse } from '../api/types'
import { ActionForm, Field, Modal } from './ui'

const EMPTY = { first_name: '', last_name: '', phone: '+998', branch_id: '' }

/** Owner/scanner adds a walk-in client (no Telegram needed): the client goes
 * straight to the END of the queue and gets a QR + 4-letter code to keep. */
export function WalkinModal({
  eventId,
  branches,
  onClose,
  onAdded,
}: {
  eventId: number
  branches: EventBranch[]
  onClose: () => void
  onAdded?: () => void
}) {
  const [form, setForm] = useState(EMPTY)
  const [result, setResult] = useState<WalkinResponse | null>(null)

  if (result) {
    const ticket = result.ticket
    return (
      <Modal title="Mijoz navbatga qo‘shildi" onClose={onClose}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ font: '400 52px/1 var(--display)', letterSpacing: '0.06em', margin: '6px 0 2px' }}>
            {ticket.number}
          </div>
          <div style={{ fontWeight: 600 }}>
            {ticket.first_name} {ticket.last_name}
          </div>
          <p className="hint" style={{ marginTop: 4 }}>
            Navbat oxiriga qo‘shildi. QR kodni mijozga ko‘rsating yoki suratga oldiring —
            kod bir marta ishlatiladi.
          </p>
          <img
            src={result.qr}
            alt={`№${ticket.number} QR kodi`}
            style={{ width: 180, height: 180, borderRadius: 'var(--r-sm)', background: '#fff', padding: 6 }}
          />
        </div>
        <div className="modal-actions">
          <button
            className="btn ghost"
            onClick={() => {
              setResult(null)
              setForm(EMPTY)
            }}
          >
            Yana qo‘shish
          </button>
          <button className="btn" onClick={onClose}>
            Yopish
          </button>
        </div>
      </Modal>
    )
  }

  return (
    <Modal
      title="Mijoz qo‘shish"
      description="Telegramsiz kelgan mijoz uchun: F.I.Sh. va telefon kiritiladi — mijoz avtomatik navbat oxiriga qo‘shiladi."
      onClose={onClose}
    >
      <ActionForm
        onSubmit={async () => {
          const added = await api<WalkinResponse>(`/queue/${eventId}/walkin`, {
            body: {
              first_name: form.first_name,
              last_name: form.last_name,
              phone: form.phone,
              branch_id: form.branch_id ? Number(form.branch_id) : null,
            },
          })
          setResult(added)
          onAdded?.()
        }}
      >
        {(busy, error) => (
          <>
            <Field label="Ism">
              <input
                className="input"
                value={form.first_name}
                onChange={(e) => setForm((f) => ({ ...f, first_name: e.target.value }))}
                required
                minLength={2}
              />
            </Field>
            <Field label="Familiya">
              <input
                className="input"
                value={form.last_name}
                onChange={(e) => setForm((f) => ({ ...f, last_name: e.target.value }))}
              />
            </Field>
            <Field label="Telefon raqam (+998)">
              <input
                className="input"
                value={form.phone}
                onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))}
                required
              />
            </Field>
            {branches.length > 0 && (
              <Field label="Filial">
                <select
                  className="input"
                  value={form.branch_id}
                  onChange={(e) => setForm((f) => ({ ...f, branch_id: e.target.value }))}
                >
                  <option value="">O‘z filialim</option>
                  {branches.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.name}
                    </option>
                  ))}
                </select>
              </Field>
            )}
            {error && <div className="error-text">{error}</div>}
            <div className="modal-actions">
              <button type="button" className="btn ghost" onClick={onClose}>
                Bekor qilish
              </button>
              <button className="btn" disabled={busy}>
                {busy ? 'Qo‘shilmoqda…' : 'Navbatga qo‘shish'}
              </button>
            </div>
          </>
        )}
      </ActionForm>
    </Modal>
  )
}
