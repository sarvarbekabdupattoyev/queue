import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api/client'
import type { EmployeeWithPassword, Role, User } from '../api/types'
import { IconPlus } from '../components/icons'
import { ActionForm, CopyButton, Field, Modal, Spinner, useToast } from '../components/ui'
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
  const { data: employees, isLoading } = useQuery({
    queryKey: ['employees'],
    queryFn: () => api<User[]>('/employees'),
  })
  const [creating, setCreating] = useState(false)
  const [reveal, setReveal] = useState<EmployeeWithPassword | null>(null)
  const [form, setForm] = useState({ first_name: '', last_name: '', phone: '+998', role: 'manager' as Role })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['employees'] })

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
      <div className="page-head">
        <div>
          <h1>Xodimlar</h1>
          <div className="sub">Menejerlar stollarda mijoz chaqiradi, skanerlar qabulxonada QR o‘qiydi</div>
        </div>
        <button className="btn" onClick={() => setCreating(true)}>
          <IconPlus size={16} /> Xodim qo‘shish
        </button>
      </div>

      <div className="card">
        {isLoading ? (
          <Spinner />
        ) : !employees?.length ? (
          <div className="empty">
            Hozircha xodimlar yo‘q. Menejer yoki QR skaner qo‘shing — parol avtomatik yaratiladi.
          </div>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Ism</th>
                  <th>Telefon</th>
                  <th>Rol</th>
                  <th>Holat</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {employees.map((employee) => (
                  <tr key={employee.id}>
                    <td>
                      {employee.first_name} {employee.last_name}
                    </td>
                    <td className="muted">{prettyPhone(employee.phone)}</td>
                    <td>
                      <span className={`badge ${employee.role === 'manager' ? 'blue' : 'teal'}`}>
                        {ROLE_LABEL[employee.role]}
                      </span>
                    </td>
                    <td>
                      <span className={`badge ${employee.is_active ? 'teal' : 'dim'}`}>
                        {employee.is_active ? 'Faol' : 'Bloklangan'}
                      </span>
                    </td>
                    <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                      <button
                        className="btn ghost sm"
                        onClick={() => resetPassword.mutate(employee)}
                        disabled={resetPassword.isPending}
                      >
                        Parolni yangilash
                      </button>{' '}
                      <button className="btn ghost sm" onClick={() => toggleActive.mutate(employee)}>
                        {employee.is_active ? 'Bloklash' : 'Faollashtirish'}
                      </button>{' '}
                      <button
                        className="btn danger-ghost sm"
                        onClick={() => {
                          if (window.confirm(`${employee.first_name} o‘chirilsinmi?`)) remove.mutate(employee)
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

      {creating && (
        <Modal title="Yangi xodim" onClose={() => setCreating(false)}>
          <ActionForm
            onSubmit={async () => {
              const created = await api<EmployeeWithPassword>('/employees', { body: form })
              setCreating(false)
              setForm({ first_name: '', last_name: '', phone: '+998', role: 'manager' })
              setReveal(created)
              invalidate()
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
