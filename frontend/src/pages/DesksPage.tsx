import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api/client'
import type { Branch, Desk, User } from '../api/types'
import { IconPlus } from '../components/icons'
import { ActionForm, Field, Modal, Spinner, useToast } from '../components/ui'

export default function DesksPage() {
  const queryClient = useQueryClient()
  const toast = useToast()
  const { data: desks, isLoading } = useQuery({
    queryKey: ['desks'],
    queryFn: () => api<Desk[]>('/desks'),
  })
  const { data: employees } = useQuery({
    queryKey: ['employees'],
    queryFn: () => api<User[]>('/employees'),
  })
  const { data: branches } = useQuery({
    queryKey: ['branches'],
    queryFn: () => api<Branch[]>('/branches'),
  })
  const hasBranches = (branches?.length ?? 0) > 0

  const [editing, setEditing] = useState<Desk | 'new' | null>(null)
  const [form, setForm] = useState({ number: 1, name: '', manager_id: '', branch_id: '' })
  // managers must belong to the desk's branch (branch-less managers fit anywhere)
  const managers = (employees ?? []).filter(
    (e) =>
      e.role === 'manager' &&
      e.is_active &&
      (!form.branch_id || e.branch_id === null || e.branch_id === Number(form.branch_id)),
  )

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['desks'] })
    queryClient.invalidateQueries({ queryKey: ['branches'] })
  }
  const remove = useMutation({
    mutationFn: (desk: Desk) => api(`/desks/${desk.id}`, { method: 'DELETE' }),
    onSuccess: () => {
      invalidate()
      toast('Stol o‘chirildi')
    },
    onError: (e: Error) => toast(e.message, true),
  })

  const openNew = () => {
    const nextNumber = (desks?.reduce((max, d) => Math.max(max, d.number), 0) ?? 0) + 1
    setForm({ number: nextNumber, name: '', manager_id: '', branch_id: '' })
    setEditing('new')
  }
  const openEdit = (desk: Desk) => {
    setForm({
      number: desk.number,
      name: desk.name,
      manager_id: desk.manager_id?.toString() ?? '',
      branch_id: desk.branch_id?.toString() ?? '',
    })
    setEditing(desk)
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Stollar</h1>
          <div className="sub">
            {hasBranches
              ? 'Mijozlar shu stollarga chaqiriladi — har bir stolni filialga va menejerga biriktiring'
              : 'Har bir menejer stoli — mijozlar shu stollarga chaqiriladi'}
          </div>
        </div>
        <button className="btn" onClick={openNew}>
          <IconPlus size={16} /> Stol qo‘shish
        </button>
      </div>

      <div className="card">
        {isLoading ? (
          <Spinner />
        ) : !desks?.length ? (
          <div className="empty">Hozircha stollar yo‘q. Kamida bitta stol qo‘shing.</div>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Raqam</th>
                  {hasBranches && <th>Filial</th>}
                  <th>Nomi</th>
                  <th>Menejer</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {desks.map((desk) => (
                  <tr key={desk.id}>
                    <td className="num">{desk.number}-stol</td>
                    {hasBranches && (
                      <td>
                        {desk.branch_name ?? <span className="badge amber">filialsiz</span>}
                      </td>
                    )}
                    <td className="muted">{desk.name || '—'}</td>
                    <td>{desk.manager_name ?? <span className="muted">biriktirilmagan</span>}</td>
                    <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                      <button className="btn ghost sm" onClick={() => openEdit(desk)}>
                        Tahrirlash
                      </button>{' '}
                      <button
                        className="btn danger-ghost sm"
                        onClick={() => {
                          if (window.confirm(`${desk.number}-stol o‘chirilsinmi?`)) remove.mutate(desk)
                        }}
                      >
                        O‘chirish
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {editing && (
        <Modal
          title={editing === 'new' ? 'Yangi stol' : `${editing.number}-stolni tahrirlash`}
          onClose={() => setEditing(null)}
        >
          <ActionForm
            onSubmit={async () => {
              const payload = {
                number: form.number,
                name: form.name,
                manager_id: form.manager_id ? Number(form.manager_id) : null,
                branch_id: form.branch_id ? Number(form.branch_id) : null,
                ...(editing !== 'new' && !form.manager_id ? { clear_manager: true } : {}),
                ...(editing !== 'new' && !form.branch_id ? { clear_branch: true } : {}),
              }
              if (editing === 'new') await api<Desk>('/desks', { body: payload })
              else await api<Desk>(`/desks/${editing.id}`, { method: 'PATCH', body: payload })
              setEditing(null)
              invalidate()
            }}
          >
            {(busy, error) => (
              <>
                {hasBranches && (
                  <Field label="Filial">
                    <select
                      className="input"
                      value={form.branch_id}
                      onChange={(e) =>
                        setForm((f) => ({ ...f, branch_id: e.target.value, manager_id: '' }))
                      }
                    >
                      <option value="">— filialsiz —</option>
                      {(branches ?? []).map((b) => (
                        <option key={b.id} value={b.id}>
                          {b.name}
                        </option>
                      ))}
                    </select>
                  </Field>
                )}
                <Field label="Stol raqami">
                  <input
                    className="input"
                    type="number"
                    min={1}
                    max={999}
                    value={form.number}
                    onChange={(e) => setForm((f) => ({ ...f, number: Number(e.target.value) }))}
                    required
                  />
                </Field>
                <Field label="Nomi (ixtiyoriy)">
                  <input
                    className="input"
                    value={form.name}
                    onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                    placeholder="Masalan: Shartnoma bo‘limi"
                  />
                </Field>
                <Field label="Menejer">
                  <select
                    className="input"
                    value={form.manager_id}
                    onChange={(e) => setForm((f) => ({ ...f, manager_id: e.target.value }))}
                  >
                    <option value="">— biriktirilmagan —</option>
                    {managers.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.first_name} {m.last_name}
                      </option>
                    ))}
                  </select>
                </Field>
                {hasBranches && (
                  <p className="hint">
                    Filialli tadbirlarda faqat filialga biriktirilgan stollar mijoz chaqira oladi;
                    ro‘yxatda shu filial menejerlarigina ko‘rinadi.
                  </p>
                )}
                {error && <div className="error-text">{error}</div>}
                <div className="modal-actions">
                  <button type="button" className="btn ghost" onClick={() => setEditing(null)}>
                    Bekor qilish
                  </button>
                  <button className="btn" disabled={busy}>
                    Saqlash
                  </button>
                </div>
              </>
            )}
          </ActionForm>
        </Modal>
      )}
    </>
  )
}
