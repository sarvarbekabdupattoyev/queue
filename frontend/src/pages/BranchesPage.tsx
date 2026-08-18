import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api/client'
import type { Branch } from '../api/types'
import { useCompany } from '../components/DashboardLayout'
import { IconBuilding, IconPlus } from '../components/icons'
import { ActionForm, EmptyState, Field, Modal, Spinner, useConfirm, useToast } from '../components/ui'

export default function BranchesPage() {
  const queryClient = useQueryClient()
  const toast = useToast()
  const confirm = useConfirm()
  const { data: company } = useCompany()
  const { data: branches, isLoading } = useQuery({
    queryKey: ['branches'],
    queryFn: () => api<Branch[]>('/branches'),
  })

  const [editing, setEditing] = useState<Branch | 'new' | null>(null)
  const [form, setForm] = useState({ name: '', address: '' })

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['branches'] })
    // events carry a branch label — keep their lists in sync
    queryClient.invalidateQueries({ queryKey: ['events'] })
  }
  const remove = useMutation({
    mutationFn: (branch: Branch) => api(`/branches/${branch.id}`, { method: 'DELETE' }),
    onSuccess: () => {
      invalidate()
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
      <div className="page-actions">
        <span className="hint">
          Filiallar ixtiyoriy. Bot bitta —{' '}
          {company?.telegram_bot_username ? `@${company.telegram_bot_username}` : 'kompaniya boti'}{' '}
          barcha filiallar uchun ro‘yxatga oladi; tadbirga filial biriktirsangiz, bot mijozga qaysi
          manzilga kelishini ko‘rsatadi.
        </span>
        <button className="btn push" onClick={openNew}>
          <IconPlus size={15} /> Filial qo‘shish
        </button>
      </div>

      <div className="card">
        {isLoading ? (
          <Spinner />
        ) : !branches?.length ? (
          <EmptyState
            icon={IconBuilding}
            action={
              <button className="btn" onClick={openNew}>
                <IconPlus size={15} /> Filial qo‘shish
              </button>
            }
          >
            Filiallar hali qo‘shilmagan — bu ixtiyoriy. Bitta ofis bo‘lsa, filialsiz davom
            etavering; bir nechta manzil bo‘lsa, filiallarni kiritib tadbirlarga biriktiring.
          </EmptyState>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Filial</th>
                  <th>Manzil</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {branches.map((branch) => (
                  <tr key={branch.id}>
                    <td className="cell-main">{branch.name}</td>
                    <td className="muted">{branch.address || '—'}</td>
                    <td>
                      <span className="row-actions">
                        <button className="btn ghost sm" onClick={() => openEdit(branch)}>
                          Tahrirlash
                        </button>
                        <button
                          className="btn danger-ghost sm"
                          onClick={async () => {
                            if (
                              await confirm({
                                title: `«${branch.name}» o‘chirilsinmi?`,
                                description:
                                  'Filialga biriktirilgan tadbirlar o‘chmaydi — ular shunchaki filialsiz qoladi.',
                              })
                            )
                              remove.mutate(branch)
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
          title={editing === 'new' ? 'Yangi filial' : 'Filialni tahrirlash'}
          description="Bot xabarlarida va tadbirlar ro‘yxatida ko‘rinadi."
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
                    placeholder="Masalan: Chilonzor"
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
