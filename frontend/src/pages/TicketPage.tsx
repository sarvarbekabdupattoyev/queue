import { useQuery } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import type { PublicTicket, TicketStatus } from '../api/types'
import { Spinner } from '../components/ui'
import { formatDateTime } from '../lib/format'

const STATUS_TEXT: Record<TicketStatus, string> = {
  registered: 'Ro‘yxatdan o‘tgansiz — ofisga kelganda QR-kodni ko‘rsating',
  checked_in: 'Keldingiz — navbatingizni kuting',
  called: 'Sizni chaqirishdi!',
  serving: 'Xizmat ko‘rsatilmoqda',
  done: 'Xizmat yakunlandi. Rahmat!',
  skipped: 'Chaqiruvda bo‘lmadingiz — qabulxonada QR-ni qayta ko‘rsating',
  cancelled: 'Navbat bekor qilingan',
}

async function fetchTicket(code: string): Promise<PublicTicket> {
  const response = await fetch(`/api/public/tickets/${code}`)
  if (!response.ok) throw new Error('Navbat topilmadi')
  return response.json()
}

export default function TicketPage() {
  const { code } = useParams()
  const { data, isLoading, error } = useQuery({
    queryKey: ['public-ticket', code],
    queryFn: () => fetchTicket(code!),
    enabled: !!code,
    refetchInterval: 10000,
  })

  if (isLoading) return <Spinner />
  if (error || !data)
    return (
      <div className="ticket-shell">
        <div className="ticket-card">
          <p>Navbat topilmadi.</p>
        </div>
      </div>
    )

  return (
    <div className="ticket-shell">
      <span className="blobs" aria-hidden="true">
        <i />
        <i />
      </span>
      <div className="ticket-card">
        <div className="brand-sub">
          {data.event.name}
          {data.branch_name && (
            <>
              <br />
              <span className="badge dim" style={{ marginTop: 6 }}>
                {data.branch_name}
                {data.branch_address ? ` · ${data.branch_address}` : ''}
              </span>
            </>
          )}
        </div>
        <div className="number">№{data.number}</div>
        <div className="muted">{data.first_name}, sizning navbat kodingiz</div>
        <img className="qr" src={data.qr} alt={`№${data.number} QR kodi`} />
        <p style={{ fontWeight: 600 }}>{STATUS_TEXT[data.status]}</p>
        {data.status === 'checked_in' && data.position !== null && (
          <p className="hint" style={{ marginTop: 8 }}>
            Sizdan oldin <b>{data.position - 1}</b> kishi bor · jami kutayotganlar:{' '}
            {data.waiting_count}
            {data.late && ' · kun oxiri navbati'}
          </p>
        )}
        {data.status === 'called' && data.desk_number !== null && (
          <p style={{ marginTop: 8, color: 'var(--amber)', fontWeight: 700, fontSize: 20 }}>
            {data.desk_number}-stolga yaqinlashing
          </p>
        )}
        {data.status === 'registered' && (
          <p className="hint" style={{ marginTop: 8 }}>
            Skanerlash {formatDateTime(data.event.checkin_until)} gacha
          </p>
        )}
      </div>
    </div>
  )
}
