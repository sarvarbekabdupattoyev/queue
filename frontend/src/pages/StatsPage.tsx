import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { StatsOverview } from '../api/types'
import { BarChart, Donut, LineChart } from '../components/charts'
import { IconCalendar, IconChart } from '../components/icons'
import { EmptyState, Spinner } from '../components/ui'
import { formatDateTime } from '../lib/format'

const RANGES = [7, 14, 30, 90] as const

function pct(part: number, whole: number): string {
  if (whole === 0) return '—'
  return `${Math.round((part / whole) * 100)}%`
}

function truncate(value: string, max = 14): string {
  return value.length > max ? `${value.slice(0, max - 1)}…` : value
}

export default function StatsPage() {
  const [days, setDays] = useState<(typeof RANGES)[number]>(14)
  const { data, isLoading, isError } = useQuery({
    queryKey: ['stats', days],
    queryFn: () => api<StatsOverview>(`/stats/overview?days=${days}`),
  })

  if (isLoading) return <Spinner />
  if (isError || !data)
    return (
      <div className="card">
        <div className="empty">Statistikani yuklab bo‘lmadi. Sahifani yangilab ko‘ring.</div>
      </div>
    )

  const { totals } = data
  const inProgress = Math.max(0, totals.arrived - totals.served - totals.skipped)
  const notArrived = Math.max(0, totals.registered - totals.arrived)
  const hasAnything = totals.events > 0

  return (
    <>
      <div className="page-actions">
        <span className="hint">Davr:</span>
        <div className="seg" role="group" aria-label="Davr">
          {RANGES.map((r) => (
            <button
              key={r}
              type="button"
              className={days === r ? 'active' : ''}
              aria-pressed={days === r}
              onClick={() => setDays(r)}
            >
              {r} kun
            </button>
          ))}
        </div>
      </div>

      {!hasAnything ? (
        <div className="card">
          <EmptyState
            icon={IconChart}
            action={
              <Link className="btn" to="/dashboard/events">
                Tadbir e’lon qilish
              </Link>
            }
          >
            Hozircha statistika yo‘q — birinchi sotuv tadbirini e’lon qiling, mijozlar bot orqali
            ro‘yxatdan o‘tishni boshlaganda raqamlar shu yerda ko‘rinadi.
          </EmptyState>
        </div>
      ) : (
        <>
          <div className="card">
            <div className="card-title">
              Umumiy ko‘rsatkichlar
              <span className="aux">so‘nggi {data.days} kun</span>
            </div>
            <div className="kpi">
              <div>
                <div className="big">{totals.registered}</div>
                <div className="delta">ro‘yxatdan o‘tgan</div>
              </div>
              <div>
                <div className="big">{totals.arrived}</div>
                <div className="delta">
                  kelgan · <b>{pct(totals.arrived, totals.registered)}</b>
                </div>
              </div>
              <div>
                <div className="big">{totals.served}</div>
                <div className="delta">
                  xizmat yakunlangan · <b>{pct(totals.served, totals.arrived)}</b>
                </div>
              </div>
              <div>
                <div className="big">{totals.contracts}</div>
                <div className="delta">
                  shartnoma tuzilgan · <b>{pct(totals.contracts, totals.served)}</b>
                </div>
              </div>
              <div>
                <div className="big">
                  {data.avg_wait_minutes ?? '—'}
                  {data.avg_wait_minutes !== null && <span style={{ fontSize: 18 }}> daq</span>}
                </div>
                <div className="delta">o‘rtacha kutish</div>
              </div>
              <div>
                <div className="big">
                  {data.avg_service_minutes ?? '—'}
                  {data.avg_service_minutes !== null && <span style={{ fontSize: 18 }}> daq</span>}
                </div>
                <div className="delta">o‘rtacha xizmat</div>
              </div>
            </div>
          </div>

          <div className="grid-2" style={{ marginTop: 16 }}>
            <div className="card">
              <div className="card-title">Kunlik dinamika</div>
              <LineChart
                labels={data.daily.map((d) => d.label)}
                series={[
                  { name: 'Yozilganlar', color: 'var(--pastel-blue2)', values: data.daily.map((d) => d.registered) },
                  { name: 'Kelganlar', color: 'var(--pastel-green2)', values: data.daily.map((d) => d.arrived) },
                  { name: 'Yakunlanganlar', color: 'var(--pastel-pink2)', values: data.daily.map((d) => d.served) },
                  { name: 'Shartnomalar', color: 'var(--pastel-cream2)', values: data.daily.map((d) => d.contracts) },
                ]}
                height={200}
              />
            </div>

            <div className="card">
              <div className="card-title">Mijozlar taqsimoti</div>
              <Donut
                centerLabel="mijoz"
                items={[
                  { label: 'Xizmat yakunlangan', value: totals.served, color: 'var(--pastel-green2)' },
                  { label: 'Jarayonda / kutmoqda', value: inProgress, color: 'var(--pastel-blue2)' },
                  { label: 'Chaqiruvda kelmagan', value: totals.skipped, color: 'var(--pastel-pink2)' },
                  { label: 'Ofisga kelmagan', value: notArrived, color: 'var(--pastel-cream2)' },
                ]}
              />
              <p className="hint" style={{ marginTop: 14 }}>
                Kun oxiri navbatiga tushganlar: <b className="mono">{totals.late}</b> · bekor
                qilinganlar: <b className="mono">{totals.cancelled}</b> · shartnoma tuzilgan:{' '}
                <b className="mono">{totals.contracts}</b> · shartnomasiz yakunlangan:{' '}
                <b className="mono">{totals.no_contract}</b>
              </p>
            </div>
          </div>

          <div className="grid-2" style={{ marginTop: 16 }}>
            <div className="card">
              <div className="card-title">
                So‘nggi tadbirlar
                <span className="aux">yozilgan va kelganlar</span>
              </div>
              {data.events.length === 0 ? (
                <div className="empty">Tadbirlar hali yo‘q</div>
              ) : (
                <BarChart
                  labels={data.events.map((e) => truncate(e.name, 10))}
                  tipTitle={(i) =>
                    `${data.events[i].name} · ${formatDateTime(data.events[i].starts_at).slice(0, 10)}`
                  }
                  series={[
                    { name: 'Yozilganlar', color: 'var(--pastel-blue)', values: data.events.map((e) => e.registered) },
                    { name: 'Kelganlar', color: 'var(--pastel-green2)', values: data.events.map((e) => e.arrived) },
                    { name: 'Shartnomalar', color: 'var(--pastel-cream2)', values: data.events.map((e) => e.contracts) },
                  ]}
                  height={220}
                />
              )}
            </div>

            <div className="card">
              <div className="card-title">
                Ro‘yxat soatlari
                <span className="aux">mijozlar botga qachon yoziladi</span>
              </div>
              <BarChart
                labels={data.hourly.map((h) => `${h.hour}:00`)}
                series={[
                  { name: 'Yozilganlar', color: 'var(--pastel-cream2)', values: data.hourly.map((h) => h.registered) },
                ]}
                height={200}
              />
            </div>
          </div>

          {data.branches.length > 0 && (
            <div className="card" style={{ marginTop: 16 }}>
              <div className="card-title">
                Filiallar kesimida
                <span className="aux">
                  <IconCalendar size={13} /> so‘nggi {data.days} kun
                </span>
              </div>
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Filial</th>
                      <th style={{ textAlign: 'right' }}>Tadbirlar</th>
                      <th style={{ textAlign: 'right' }}>Yozilgan</th>
                      <th style={{ textAlign: 'right' }}>Kelgan</th>
                      <th style={{ textAlign: 'right' }}>Yakunlangan</th>
                      <th style={{ textAlign: 'right' }}>Shartnoma</th>
                      <th style={{ textAlign: 'right' }}>Kelish darajasi</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.branches.map((b) => (
                      <tr key={b.id}>
                        <td className="cell-main">{b.name}</td>
                        <td className="mono" style={{ textAlign: 'right' }}>{b.events}</td>
                        <td className="mono" style={{ textAlign: 'right' }}>{b.registered}</td>
                        <td className="mono" style={{ textAlign: 'right' }}>{b.arrived}</td>
                        <td className="mono" style={{ textAlign: 'right' }}>{b.served}</td>
                        <td className="mono" style={{ textAlign: 'right' }}>{b.contracts}</td>
                        <td style={{ textAlign: 'right' }}>
                          <span className="badge teal">{pct(b.arrived, b.registered)}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </>
  )
}
