import { useRef, useState, type ReactNode } from 'react'

/**
 * Hand-rolled SVG charts in the house style: pastel fills, generously
 * rounded bar tops, dashed reference lines and a floating white tooltip.
 * Everything is drawn with design tokens, so both themes just work.
 */

export interface ChartSeries {
  name: string
  color: string // CSS value, e.g. 'var(--pastel-blue)'
  values: number[]
}

const VIEW_W = 640

function niceMax(values: number[]): number {
  const max = Math.max(0, ...values)
  return max === 0 ? 1 : max
}

/** Bar with big rounded shoulders on top, small feet at the bottom. */
function barPath(x: number, y: number, w: number, h: number): string {
  const rt = Math.min(w / 2, 11)
  const rb = Math.min(w / 2, 4, h / 2)
  const bottom = y + h
  if (h <= rt) {
    const r = Math.max(1, h / 2)
    return `M${x},${bottom} L${x},${y + r} Q${x},${y} ${x + r},${y} L${x + w - r},${y} Q${x + w},${y} ${x + w},${y + r} L${x + w},${bottom} Z`
  }
  return [
    `M${x + rb},${bottom}`,
    `L${x},${bottom - rb} L${x},${y + rt}`,
    `Q${x},${y} ${x + rt},${y}`,
    `L${x + w - rt},${y}`,
    `Q${x + w},${y} ${x + w},${y + rt}`,
    `L${x + w},${bottom - rb}`,
    `L${x + w - rb},${bottom} Z`,
  ].join(' ')
}

function useTip() {
  const wrapRef = useRef<HTMLDivElement>(null)
  const [tip, setTip] = useState<{ index: number; left: number } | null>(null)
  const place = (index: number, viewX: number, tipWidth = 168) => {
    const width = wrapRef.current?.clientWidth ?? VIEW_W
    const left = Math.max(0, Math.min((viewX / VIEW_W) * width + 10, width - tipWidth))
    setTip({ index, left })
  }
  return { wrapRef, tip, place, clear: () => setTip(null) }
}

function Tip({ left, children }: { left: number; children: ReactNode }) {
  return (
    <div className="chart-tip" role="tooltip" style={{ left, top: 0 }}>
      {children}
    </div>
  )
}

function Legend({ series }: { series: ChartSeries[] }) {
  return (
    <ul className="chart-legend">
      {series.map((s) => (
        <li key={s.name}>
          <span className="legend-dot" style={{ background: s.color }} />
          {s.name}
        </li>
      ))}
    </ul>
  )
}

/** Grouped bars per label with a dashed line resting on the tallest bar. */
export function BarChart({
  labels,
  series,
  height = 210,
  tipTitle,
}: {
  labels: string[]
  series: ChartSeries[]
  height?: number
  tipTitle?: (index: number) => string
}) {
  const { wrapRef, tip, place, clear } = useTip()
  const axisH = 18
  const plotH = height - axisH
  const max = niceMax(series.flatMap((s) => s.values))
  const n = Math.max(labels.length, 1)
  const slot = VIEW_W / n
  const groupW = Math.min(slot * 0.62, 26 * series.length + 6)
  const barW = (groupW - (series.length - 1) * 4) / series.length
  const top = 14
  const labelStep = Math.ceil(n / 12)

  const y = (v: number) => top + (plotH - top) * (1 - v / max)
  const dashY = y(max)

  return (
    <div className="chart-wrap" ref={wrapRef} onMouseLeave={clear}>
      <svg viewBox={`0 0 ${VIEW_W} ${height}`} role="img" aria-label="Diagramma">
        <line
          x1={0}
          x2={VIEW_W}
          y1={dashY}
          y2={dashY}
          stroke="var(--line-strong)"
          strokeDasharray="5 5"
        />
        {labels.map((label, i) => {
          const cx = slot * i + slot / 2
          const x0 = cx - groupW / 2
          const active = tip?.index === i
          return (
            <g key={i} opacity={tip === null || active ? 1 : 0.45}>
              {series.map((s, si) => {
                const v = s.values[i] ?? 0
                const by = y(v)
                return (
                  <path
                    key={s.name}
                    d={barPath(x0 + si * (barW + 4), by, barW, plotH - by)}
                    fill={s.color}
                  />
                )
              })}
              {i % labelStep === 0 && (
                <text x={cx} y={height - 4} textAnchor="middle" className="chart-axis">
                  {label}
                </text>
              )}
              <rect
                x={slot * i}
                y={0}
                width={slot}
                height={plotH}
                fill="transparent"
                onMouseEnter={() => place(i, cx)}
                onClick={() => place(i, cx)}
              />
            </g>
          )
        })}
      </svg>
      {tip && (
        <Tip left={tip.left}>
          <p className="tt">{tipTitle ? tipTitle(tip.index) : labels[tip.index]}</p>
          <ul>
            {series.map((s) => (
              <li key={s.name}>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                  <span className="legend-dot" style={{ background: s.color }} />
                  {s.name}
                </span>
                <b>{s.values[tip.index] ?? 0}</b>
              </li>
            ))}
          </ul>
        </Tip>
      )}
      <Legend series={series} />
    </div>
  )
}

/** Catmull-Rom smoothing, same curve feel as the reference line chart. */
function smoothPath(points: { x: number; y: number }[]): string {
  if (points.length === 0) return ''
  if (points.length === 1) return `M${points[0].x},${points[0].y}`
  let d = `M${points[0].x},${points[0].y}`
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[i - 1] ?? points[i]
    const p1 = points[i]
    const p2 = points[i + 1]
    const p3 = points[i + 2] ?? p2
    const c1x = p1.x + (p2.x - p0.x) / 6
    const c1y = p1.y + (p2.y - p0.y) / 6
    const c2x = p2.x - (p3.x - p1.x) / 6
    const c2y = p2.y - (p3.y - p1.y) / 6
    d += ` C${c1x},${c1y} ${c2x},${c2y} ${p2.x},${p2.y}`
  }
  return d
}

/** Smooth multi-series line with a dashed day indicator on hover. */
export function LineChart({
  labels,
  series,
  height = 180,
  fillFirst = true,
}: {
  labels: string[]
  series: ChartSeries[]
  height?: number
  fillFirst?: boolean
}) {
  const { wrapRef, tip, place, clear } = useTip()
  const axisH = 18
  const plotH = height - axisH
  const max = niceMax(series.flatMap((s) => s.values))
  const n = Math.max(labels.length, 1)
  const pad = 10
  const step = n > 1 ? (VIEW_W - pad * 2) / (n - 1) : 0
  const xAt = (i: number) => (n > 1 ? pad + step * i : VIEW_W / 2)
  const yAt = (v: number) => 14 + (plotH - 20) * (1 - v / max)
  const labelStep = Math.ceil(n / 8)

  const pointsFor = (s: ChartSeries) => labels.map((_, i) => ({ x: xAt(i), y: yAt(s.values[i] ?? 0) }))

  return (
    <div className="chart-wrap" ref={wrapRef} onMouseLeave={clear}>
      <svg viewBox={`0 0 ${VIEW_W} ${height}`} role="img" aria-label="Grafik">
        {fillFirst && series[0] && (
          <path
            d={`${smoothPath(pointsFor(series[0]))} L${xAt(n - 1)},${plotH} L${xAt(0)},${plotH} Z`}
            fill={series[0].color}
            opacity={0.18}
          />
        )}
        {series.map((s, si) => (
          <path
            key={s.name}
            d={smoothPath(pointsFor(s))}
            fill="none"
            stroke={s.color}
            strokeWidth={2}
            strokeDasharray={si > 0 && si === series.length - 1 && series.length > 2 ? '4 4' : undefined}
          />
        ))}
        {tip !== null && (
          <line
            x1={xAt(tip.index)}
            x2={xAt(tip.index)}
            y1={8}
            y2={plotH}
            stroke="var(--line-strong)"
            strokeDasharray="3 4"
          />
        )}
        {tip !== null &&
          series.map((s) => (
            <circle
              key={s.name}
              cx={xAt(tip.index)}
              cy={yAt(s.values[tip.index] ?? 0)}
              r={4.5}
              fill={s.color}
              stroke="var(--surface)"
              strokeWidth={2}
            />
          ))}
        {labels.map((label, i) =>
          i % labelStep === 0 ? (
            <text
              key={i}
              x={xAt(i)}
              y={height - 4}
              textAnchor={i === 0 ? 'start' : i === n - 1 ? 'end' : 'middle'}
              className="chart-axis"
            >
              {label}
            </text>
          ) : null,
        )}
        {labels.map((_, i) => (
          <rect
            key={i}
            x={xAt(i) - (step || VIEW_W) / 2}
            y={0}
            width={step || VIEW_W}
            height={plotH}
            fill="transparent"
            onMouseEnter={() => place(i, xAt(i))}
            onClick={() => place(i, xAt(i))}
          />
        ))}
      </svg>
      {tip && (
        <Tip left={tip.left}>
          <p className="tt">{labels[tip.index]}</p>
          <ul>
            {series.map((s) => (
              <li key={s.name}>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                  <span className="legend-dot" style={{ background: s.color }} />
                  {s.name}
                </span>
                <b>{s.values[tip.index] ?? 0}</b>
              </li>
            ))}
          </ul>
        </Tip>
      )}
      <Legend series={series} />
    </div>
  )
}

/** Donut with a serif total in the middle. */
export function Donut({
  items,
  centerLabel,
  size = 168,
}: {
  items: { label: string; value: number; color: string }[]
  centerLabel: string
  size?: number
}) {
  const total = items.reduce((sum, item) => sum + item.value, 0)
  const R = 58
  const C = 2 * Math.PI * R
  let offset = 0
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 20, flexWrap: 'wrap' }}>
      <svg
        width={size}
        height={size}
        viewBox="0 0 148 148"
        role="img"
        aria-label={centerLabel}
        style={{ flex: '0 0 auto' }}
      >
        <circle cx="74" cy="74" r={R} fill="none" stroke="var(--surface-2)" strokeWidth="17" />
        {total > 0 &&
          items.map((item) => {
            const frac = item.value / total
            const dash = `${frac * C} ${C}`
            const el = (
              <circle
                key={item.label}
                cx="74"
                cy="74"
                r={R}
                fill="none"
                stroke={item.color}
                strokeWidth="17"
                strokeDasharray={dash}
                strokeDashoffset={-offset * C}
                strokeLinecap={frac > 0.02 ? 'round' : 'butt'}
                transform="rotate(-90 74 74)"
              />
            )
            offset += frac
            return el
          })}
        <text
          x="74"
          y="72"
          textAnchor="middle"
          style={{ font: '400 30px var(--display)', fill: 'var(--text)' }}
        >
          {total}
        </text>
        <text x="74" y="90" textAnchor="middle" className="chart-axis">
          {centerLabel}
        </text>
      </svg>
      <ul style={{ listStyle: 'none', display: 'grid', gap: 7, fontSize: 12.5, minWidth: 150 }}>
        {items.map((item) => (
          <li
            key={item.label}
            style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16 }}
          >
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, color: 'var(--dim)' }}>
              <span className="legend-dot" style={{ background: item.color }} />
              {item.label}
            </span>
            <b className="mono" style={{ fontSize: 13 }}>
              {item.value}
            </b>
          </li>
        ))}
      </ul>
    </div>
  )
}
