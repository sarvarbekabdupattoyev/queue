import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api/client'
import type { Branch, EmployeeWithPassword, Role, User } from '../api/types'
import { IconPlus, IconUsers } from '../components/icons'
import {
  ActionForm,
  CopyButton,
  EmptyState,
  Field,
  Modal,
  Spinner,
  useConfirm,
  useToast,
} from '../components/ui'
import { prettyPhone } from '../lib/format'

const ROLE_LABEL: Record<Role, string> = {
  owner: 'Egasi',
  manager: 'Menejer',
  scanner: 'QR skaner',
}

function PasswordReveal({
  data,
  onClose,
}: {
  data: EmployeeWithPassword
  onClose: () => void
}) {
  return (
    <Modal title="Xodim paroli" onClose={onClose}>
      <p className="hint">
        {data.employee.first_name} uchun parol yaratildi. U <b>faqat bir marta</b> ko‘rsatiladi —
        nusxalab xodimga bering. Yo‘qolsa, «Parolni yangilash» tugmasidan foydalaning.
      </p>
      <div className="password-box">
        <code>{data.password}</code>
      </div>
      <p className="hint">
        Kirish: {prettyPhone(data.employee.phone)} · {ROLE_LABEL[data.employee.role]}
      </p>
      <div className="modal-actions">
        <CopyButton text={data.password} label="Parolni nusxalash" />
        <button className="btn" onClick={onClose}>
          Yopish
        </button>
      </div>
    </Modal>
  )
}

export default function EmployeesPage() {
  const queryClient = useQueryClient()
  const toast = useToast()
  const confirm = useConfirm()
  const { data: employees, isLoading } = useQuery({
    queryKey: ['employees'],
    queryFn: () => api<User[]>('/employees'),
  })
  const { data: branches } = useQuery({
    queryKey: ['branches'],
    queryFn: () => api<Branch[]>('/branches'),
  })
  const hasBranches = (branches?.length ?? 0) > 0
  const [creating, setCreating] = useState(false)
  const [reveal, setReveal] = useState<EmployeeWithPassword | null>(null)
  const [form, setForm] = useState({
    first_name: '',
    last_name: '',
    phone: '+998',
    role: 'manager' as Role,
    branch_id: '',
  })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['employees'] })

  const setBranch = useMutation({
    mutationFn: ({ employee, branchId }: { employee: User; branchId: number | null }) =>
      api<User>(`/employees/${employee.id}`, {
        method: 'PATCH',
        body: branchId === null ? { clear_branch: true } : { branch_id: branchId },
      }),
    onSuccess: () => {
      invalidate()
      queryClient.invalidateQueries({ queryKey: ['branches'] })
    },
    onError: (e: Error) => toast(e.message, true),
  })
  const toggleActive = useMutation({
    mutationFn: (employee: User) =>
      api<User>(`/employees/${employee.id}`, {
        method: 'PATCH',
        body: { is_active: !employee.is_active },
      }),
    onSuccess: invalidate,
    onError: (e: Error) => toast(e.message, true),
  })
  const resetPassword = useMutation({
    mutationFn: (employee: User) =>
      api<EmployeeWithPassword>(`/employees/${employee.id}/reset-password`, { method: 'POST' }),
    onSuccess: (data) => setReveal(data),
    onError: (e: Error) => toast(e.message, true),
  })
  const remove = useMutation({
    mutationFn: (employee: User) => api(`/employees/${employee.id}`, { method: 'DELETE' }),
    onSuccess: () => {
      invalidate()
      toast('Xodim o‘chirildi')
    },
    onError: (e: Error) => toast(e.message, true),
  })

  return (
    <>
      <div className="page-actions">
        <span className="hint">
          {hasBranches
            ? 'Menejerlar stollarda mijoz chaqiradi, skanerlar QR o‘qiydi — har bir filialga o‘z xodimlarini biriktiring'
            : 'Menejerlar stollarda mijoz chaqiradi, skanerlar qabulxonada QR o‘qiydi'}
        </span>
        <button className="btn push" onClick={() => setCreating(true)}>
          <IconPlus size={15} /> Xodim qo‘shish
        </button>
      </div>

      <div className="card">
        {isLoading ? (
          <Spinner />
        ) : !employees?.length ? (
          <EmptyState
            icon={IconUsers}
            action={
              <button className="btn" onClick={() => setCreating(true)}>
                <IconPlus size={15} /> Xodim qo‘shish
              </button>
            }
          >
            Hozircha xodimlar yo‘q. Menejer yoki QR skaner qo‘shing — parol avtomatik yaratiladi.
          </EmptyState>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Ism</th>
                  <th>Telefon</th>
                  <th>Rol</th>
                  {hasBranches && <th>Filial</th>}
                  <th>Holat</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {employees.map((employee) => (
                  <tr key={employee.id}>
                    <td className="cell-main">
                      {employee.first_name} {employee.last_name}
                    </td>
                    <td className="muted">{prettyPhone(employee.phone)}</td>
                    <td>
                      <span className={`badge ${employee.role === 'manager' ? 'blue' : 'teal'}`}>
                        {ROLE_LABEL[employee.role]}
                      </span>
                    </td>
                    {hasBranches && (
                      <td>
                        <select
                          className="input"
                          style={{ width: 'auto', minWidth: 140 }}
                          aria-label={`${employee.first_name} filiali`}
                          value={employee.branch_id ?? ''}
                          disabled={setBranch.isPending}
                          onChange={(e) =>
                            setBranch.mutate({
                              employee,
                              branchId: e.target.value ? Number(e.target.value) : null,
                            })
                          }
                        >
                          <option value="">Barcha filiallar</option>
                          {(branches ?? []).map((b) => (
                            <option key={b.id} value={b.id}>
                              {b.name}
                            </option>
                          ))}
                        </select>
                      </td>
                    )}
                    <td>
                      <span className={`badge ${employee.is_active ? 'teal' : 'dim'}`}>
                        {employee.is_active ? 'Faol' : 'Bloklangan'}
                      </span>
                    </td>
                    <td>
                      <span className="row-actions">
                        <button
                          className="btn ghost sm"
                          onClick={() => resetPassword.mutate(employee)}
                          disabled={resetPassword.isPending}
                        >
                          Parolni yangilash
                        </button>
                        <button className="btn ghost sm" onClick={() => toggleActive.mutate(employee)}>
                          {employee.is_active ? 'Bloklash' : 'Faollashtirish'}
                        </button>
                        <button
                          className="btn danger-ghost sm"
                          onClick={async () => {
                            if (
                              await confirm({
                                title: `${employee.first_name} o‘chirilsinmi?`,
                                description: 'Xodim tizimga kira olmaydi. Bu amalni qaytarib bo‘lmaydi.',
                              })
                            )
                              remove.mutate(employee)
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

      {creating && (
        <Modal title="Yangi xodim" onClose={() => setCreating(false)}>
          <ActionForm
            onSubmit={async () => {
              const created = await api<EmployeeWithPassword>('/employees', {
                body: {
                  first_name: form.first_name,
                  last_name: form.last_name,
                  phone: form.phone,
                  role: form.role,
                  branch_id: form.branch_id ? Number(form.branch_id) : null,
                },
              })
              setCreating(false)
              setForm({ first_name: '', last_name: '', phone: '+998', role: 'manager', branch_id: '' })
              setReveal(created)
              invalidate()
              queryClient.invalidateQueries({ queryKey: ['branches'] })
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
                <Field label="Telefon raqam (login sifatida ishlatiladi)">
                  <input
                    className="input"
                    value={form.phone}
                    onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))}
                    required
                  />
                </Field>
                <Field label="Rol">
                  <select
                    className="input"
                    value={form.role}
                    onChange={(e) => setForm((f) => ({ ...f, role: e.target.value as Role }))}
                  >
                    <option value="manager">Menejer (stolda mijoz qabul qiladi)</option>
                    <option value="scanner">QR skaner (qabulxonada belgilaydi)</option>
                  </select>
                </Field>
                {hasBranches && (
                  <Field label="Filial">
                    <select
                      className="input"
                      value={form.branch_id}
                      onChange={(e) => setForm((f) => ({ ...f, branch_id: e.target.value }))}
                    >
                      <option value="">Barcha filiallar</option>
                      {(branches ?? []).map((b) => (
                        <option key={b.id} value={b.id}>
                          {b.name}
                        </option>
                      ))}
                    </select>
                  </Field>
                )}
                <p className="hint">Parol avtomatik yaratiladi va bir marta ko‘rsatiladi.</p>
                {error && <div className="error-text">{error}</div>}
                <div className="modal-actions">
                  <button type="button" className="btn ghost" onClick={() => setCreating(false)}>
                    Bekor qilish
                  </button>
                  <button className="btn" disabled={busy}>
                    {busy ? 'Qo‘shilmoqda…' : 'Qo‘shish'}
                  </button>
                </div>
              </>
            )}
          </ActionForm>
        </Modal>
      )}

      {reveal && <PasswordReveal data={reveal} onClose={() => setReveal(null)} />}
    </>
  )
}
