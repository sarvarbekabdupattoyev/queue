import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api/client'
import type { Desk, User } from '../api/types'
import { IconDesk, IconPlus } from '../components/icons'
import {
  ActionForm,
  EmptyState,
  Field,
  Modal,
  Spinner,
  useConfirm,
  useToast,
} from '../components/ui'

export default function DesksPage() {
  const queryClient = useQueryClient()
  const toast = useToast()
  const confirm = useConfirm()
  const { data: desks, isLoading } = useQuery({
    queryKey: ['desks'],
    queryFn: () => api<Desk[]>('/desks'),
  })
  const { data: employees } = useQuery({
    queryKey: ['employees'],
    queryFn: () => api<User[]>('/employees'),
  })
  const managers = employees?.filter((e) => e.role === 'manager' && e.is_active) ?? []

  const [editing, setEditing] = useState<Desk | 'new' | null>(null)
  const [form, setForm] = useState({ number: 1, name: '', manager_id: '' })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['desks'] })
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
    setForm({ number: nextNumber, name: '', manager_id: '' })
    setEditing('new')
  }
  const openEdit = (desk: Desk) => {
    setForm({ number: desk.number, name: desk.name, manager_id: desk.manager_id?.toString() ?? '' })
    setEditing(desk)
  }

  return (
    <>
      <div className="page-actions">
        <span className="hint">Har bir menejer stoli — mijozlar shu stollarga chaqiriladi</span>
        <button className="btn push" onClick={openNew}>
          <IconPlus size={15} /> Stol qo‘shish
        </button>
      </div>

      <div className="card">
        {isLoading ? (
          <Spinner />
        ) : !desks?.length ? (
          <EmptyState
            icon={IconDesk}
            action={
              <button className="btn" onClick={openNew}>
                <IconPlus size={15} /> Stol qo‘shish
              </button>
            }
          >
            Hozircha stollar yo‘q. Kamida bitta stol qo‘shing — chaqirilgan mijozlar ekranda shu
            stol raqamini ko‘radi.
          </EmptyState>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Raqam</th>
                  <th>Nomi</th>
                  <th>Menejer</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {desks.map((desk) => (
                  <tr key={desk.id}>
                    <td className="num">{desk.number}-stol</td>
                    <td className="muted">{desk.name || '—'}</td>
                    <td>{desk.manager_name ?? <span className="muted">biriktirilmagan</span>}</td>
                    <td>
                      <span className="row-actions">
                        <button className="btn ghost sm" onClick={() => openEdit(desk)}>
                          Tahrirlash
                        </button>
                        <button
                          className="btn danger-ghost sm"
                          onClick={async () => {
                            if (
                              await confirm({
                                title: `${desk.number}-stol o‘chirilsinmi?`,
                                description: 'Stolga biriktirilgan menejer boshqa stol tanlashi kerak bo‘ladi.',
                              })
                            )
                              remove.mutate(desk)
                          }}
                        >
                          O‘chirish
                        </button>
                      </span>
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
                ...(editing !== 'new' && !form.manager_id ? { clear_manager: true } : {}),
              }
              if (editing === 'new') await api<Desk>('/desks', { body: payload })
              else await api<Desk>(`/desks/${editing.id}`, { method: 'PATCH', body: payload })
              setEditing(null)
              invalidate()
            }}
          >
            {(busy, error) => (
              <>
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
