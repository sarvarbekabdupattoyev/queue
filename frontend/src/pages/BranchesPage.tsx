import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { Branch } from '../api/types'
import { IconBuilding, IconPlus } from '../components/icons'
import { ActionForm, EmptyState, Field, Modal, Spinner, useToast } from '../components/ui'

export default function BranchesPage() {
  const queryClient = useQueryClient()
  const toast = useToast()
  const { data: branches, isLoading } = useQuery({
    queryKey: ['branches'],
    queryFn: () => api<Branch[]>('/branches'),
  })
  const [editing, setEditing] = useState<Branch | 'new' | null>(null)
  const [form, setForm] = useState({ name: '', address: '' })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['branches'] })
  const remove = useMutation({
    mutationFn: (branch: Branch) => api(`/branches/${branch.id}`, { method: 'DELETE' }),
    onSuccess: () => {
      invalidate()
      queryClient.invalidateQueries({ queryKey: ['desks'] })
      queryClient.invalidateQueries({ queryKey: ['employees'] })
      toast('Filial o‘chirildi')
    },
    onError: (e: Error) => toast(e.message, true),
  })

  const openNew = () => {
    setForm({ name: '', address: '' })
    setEditing('new')
  }
  const openEdit = (branch: Branch) => {
    setForm({ name: branch.name, address: branch.address })
    setEditing(branch)
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Filiallar</h1>
          <div className="sub">
            Bir tadbir bir nechta filialda o‘tishi mumkin — har bir filialning menejerlari,
            stollari va navbati alohida bo‘ladi
          </div>
        </div>
        <button className="btn" onClick={openNew}>
          <IconPlus size={16} /> Filial qo‘shish
        </button>
      </div>

      <div className="card">
        {isLoading ? (
          <Spinner />
        ) : !branches?.length ? (
          <EmptyState icon={IconBuilding}>
            Filiallar ixtiyoriy: bitta ofis bo‘lsa, bu bo‘limni o‘tkazib yuboring. Bir nechta
            ofis bo‘lsa, avval filiallarni qo‘shing — keyin har biriga{' '}
            <Link to="/dashboard/employees">menejerlar</Link> va{' '}
            <Link to="/dashboard/desks">stollar</Link> biriktirasiz.
          </EmptyState>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Filial</th>
                  <th>Manzil</th>
                  <th>Xodimlar</th>
                  <th>Stollar</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {branches.map((branch) => (
                  <tr key={branch.id}>
                    <td style={{ fontWeight: 600 }}>{branch.name}</td>
                    <td className="muted">{branch.address || '—'}</td>
                    <td className="mono">{branch.employee_count}</td>
                    <td className="mono">{branch.desk_count}</td>
                    <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                      <button className="btn ghost sm" onClick={() => openEdit(branch)}>
                        Tahrirlash
                      </button>{' '}
                      <button
                        className="btn danger-ghost sm"
                        onClick={() => {
                          if (
                            window.confirm(
                              `«${branch.name}» o‘chirilsinmi? Filial stollari ham o‘chadi, xodimlari filialsiz qoladi.`,
                            )
                          )
                            remove.mutate(branch)
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

      {!!branches?.length && (
        <div className="card">
          <p className="hint">
            Keyingi qadam: har bir filial uchun <Link to="/dashboard/employees">menejer
            qo‘shing</Link>, so‘ng <Link to="/dashboard/desks">stollar yaratib</Link> menejerlarni
            biriktiring. Tadbir yaratayotganda kerakli filiallarni belgilaysiz — mijoz botda
            filialini tanlaydi va navbat shu filial ichida yuradi.
          </p>
        </div>
      )}

      {editing && (
        <Modal
          title={editing === 'new' ? 'Yangi filial' : 'Filialni tahrirlash'}
          onClose={() => setEditing(null)}
        >
          <ActionForm
            onSubmit={async () => {
              if (editing === 'new') await api<Branch>('/branches', { body: form })
              else await api<Branch>(`/branches/${editing.id}`, { method: 'PATCH', body: form })
              setEditing(null)
              invalidate()
            }}
          >
            {(busy, error) => (
              <>
                <Field label="Filial nomi">
                  <input
                    className="input"
                    value={form.name}
                    onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                    placeholder="Masalan: Chilonzor filiali"
                    required
                    minLength={2}
                  />
                </Field>
                <Field label="Manzil (ixtiyoriy)">
                  <input
                    className="input"
                    value={form.address}
                    onChange={(e) => setForm((f) => ({ ...f, address: e.target.value }))}
                    placeholder="Toshkent, Chilonzor 9-mavze"
                  />
                </Field>
                <p className="hint">
                  Filial nomi va manzili mijozga botda filial tanlashda ko‘rinadi.
                </p>
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
