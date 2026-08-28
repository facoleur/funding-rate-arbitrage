import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { fetchFunding, type FundingPoint } from '../api/funding'
import { fmtTime } from '../lib/format'
import { Select } from '../components/ui/Field'
import QueryState from '../components/ui/QueryState'

const INSTRUMENTS = ['BTC-PERPETUAL', 'ETH-PERPETUAL'] as const
const DAY_OPTIONS = [7, 30, 90, 365] as const

function fmt(v: number, dec = 4) {
  return v.toFixed(dec)
}

function fmtDate(ms: number) {
  return new Date(ms).toLocaleDateString('fr-FR', {
    day: '2-digit',
    month: '2-digit',
  })
}

/* ── Chart SVG ── */
function LineChart({ data, height = 160 }: { data: FundingPoint[]; height?: number }) {
  const W = 900
  const H = height
  const PAD = { top: 8, right: 8, bottom: 20, left: 50 }
  const inner = { w: W - PAD.left - PAD.right, h: H - PAD.top - PAD.bottom }

  const rates = data.map((d) => d.rate_ann)
  const minR = Math.min(...rates)
  const maxR = Math.max(...rates)
  const rangeR = maxR - minR || 0.001

  const xs = data.map((_, i) => PAD.left + (i / Math.max(data.length - 1, 1)) * inner.w)
  const ys = data.map((d) => PAD.top + (1 - (d.rate_ann - minR) / rangeR) * inner.h)

  const zero_y = PAD.top + (1 - (0 - minR) / rangeR) * inner.h
  const show_zero = zero_y > PAD.top && zero_y < PAD.top + inner.h

  const points = xs.map((x, i) => `${x},${ys[i]}`).join(' ')

  // Y axis ticks
  const ticks = 4
  const yTicks = Array.from({ length: ticks + 1 }, (_, i) => {
    const frac = i / ticks
    const val = minR + frac * rangeR
    const y = PAD.top + (1 - frac) * inner.h
    return { val, y }
  })

  // X axis labels — show ~6 evenly spaced
  const xStep = Math.max(1, Math.floor(data.length / 6))
  const xLabels = data
    .map((d, i) => ({ i, ms: d.ts }))
    .filter(({ i }) => i % xStep === 0 || i === data.length - 1)

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height }}>
      {/* zero line */}
      {show_zero && (
        <line
          x1={PAD.left}
          y1={zero_y}
          x2={PAD.left + inner.w}
          y2={zero_y}
          stroke="#3f3f46"
          strokeDasharray="4 3"
          strokeWidth={1}
        />
      )}

      {/* Y ticks */}
      {yTicks.map(({ val, y }, i) => (
        <g key={i}>
          <line x1={PAD.left - 4} y1={y} x2={PAD.left} y2={y} stroke="#52525b" strokeWidth={1} />
          <text x={PAD.left - 6} y={y + 4} textAnchor="end" fontSize={9} fill="#71717a">
            {fmt(val, 1)}%
          </text>
        </g>
      ))}

      {/* X labels */}
      {xLabels.map(({ i, ms }) => (
        <text
          key={i}
          x={xs[i]}
          y={PAD.top + inner.h + 14}
          textAnchor="middle"
          fontSize={9}
          fill="#52525b"
        >
          {fmtDate(ms)}
        </text>
      ))}

      {/* area fill */}
      <defs>
        <linearGradient id="fg" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#34d399" stopOpacity="0.15" />
          <stop offset="100%" stopColor="#34d399" stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon
        points={`${PAD.left},${PAD.top + inner.h} ${points} ${PAD.left + inner.w},${PAD.top + inner.h}`}
        fill="url(#fg)"
      />

      {/* line */}
      <polyline points={points} fill="none" stroke="#34d399" strokeWidth={1.5} />

      {/* axes */}
      <line
        x1={PAD.left}
        y1={PAD.top}
        x2={PAD.left}
        y2={PAD.top + inner.h}
        stroke="#3f3f46"
        strokeWidth={1}
      />
      <line
        x1={PAD.left}
        y1={PAD.top + inner.h}
        x2={PAD.left + inner.w}
        y2={PAD.top + inner.h}
        stroke="#3f3f46"
        strokeWidth={1}
      />
    </svg>
  )
}

/* ── Stat box ── */
function Stat({
  label,
  value,
  sub,
  color = 'text-zinc-200',
}: {
  label: string
  value: string
  sub?: string
  color?: string
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] text-zinc-600 uppercase tracking-wider">{label}</span>
      <span className={`text-sm font-semibold tabular-nums ${color}`}>{value}</span>
      {sub && <span className="text-[10px] text-zinc-600">{sub}</span>}
    </div>
  )
}

function stats(data: FundingPoint[]) {
  if (!data.length) return null
  const rates = data.map((d) => d.rate_ann)
  const avg = rates.reduce((a, b) => a + b, 0) / rates.length
  const min = Math.min(...rates)
  const max = Math.max(...rates)
  const last = data[data.length - 1]
  const pctPos = (rates.filter((r) => r >= 0).length / rates.length) * 100
  return { avg, min, max, last, pctPos }
}

export default function Funding() {
  const [instrument, setInstrument] = useState<string>('BTC-PERPETUAL')
  const [days, setDays] = useState(30)

  const {
    data = [],
    isLoading,
    dataUpdatedAt,
  } = useQuery({
    queryKey: ['funding', instrument, days],
    queryFn: () => fetchFunding({ instrument, days }),
    staleTime: 15 * 60_000,
    refetchInterval: 15 * 60_000,
  })

  const s = useMemo(() => stats(data), [data])

  const rateColor = (v: number) =>
    v >= 20
      ? 'text-emerald-400'
      : v >= 5
        ? 'text-emerald-500'
        : v >= 0
          ? 'text-zinc-400'
          : 'text-red-400'

  return (
    <div className="space-y-5">
      {/* ── Header + filtres ── */}
      <div className="flex items-center gap-3 flex-wrap">
        <h1 className="text-base font-semibold text-zinc-100 mr-1">Funding rates</h1>

        <Select value={instrument} onChange={setInstrument}>
          {INSTRUMENTS.map((i) => (
            <option key={i} value={i}>
              {i}
            </option>
          ))}
        </Select>

        <Select value={days} onChange={(v) => setDays(Number(v))}>
          {DAY_OPTIONS.map((d) => (
            <option key={d} value={d}>
              {d} jours
            </option>
          ))}
        </Select>
      </div>

      {dataUpdatedAt > 0 && (
        <p className="text-[10px] text-zinc-700">
          Mis à jour à {fmtTime(dataUpdatedAt)} · refresh auto toutes les 15 min
        </p>
      )}

      <QueryState isLoading={isLoading} />

      {s && (
        <>
          {/* ── Stats ── */}
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-4 rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
            <Stat
              label="Actuel (ann.)"
              value={`${fmt(s.last.rate_ann, 2)}%`}
              sub={`${fmt(s.last.rate_8h, 4)}% / 8h`}
              color={rateColor(s.last.rate_ann)}
            />
            <Stat label="Moyenne (ann.)" value={`${fmt(s.avg, 2)}%`} color={rateColor(s.avg)} />
            <Stat label="Min (ann.)" value={`${fmt(s.min, 2)}%`} color="text-zinc-400" />
            <Stat label="Max (ann.)" value={`${fmt(s.max, 2)}%`} color="text-zinc-400" />
            <Stat
              label="% périodes positives"
              value={`${s.pctPos.toFixed(1)}%`}
              sub="shorts reçoivent du funding"
              color={s.pctPos >= 60 ? 'text-emerald-500' : 'text-amber-400'}
            />
          </div>

          {/* ── Note hedge ── */}
          <div className="rounded border border-zinc-800 bg-zinc-900/30 px-4 py-3 text-xs text-zinc-500 space-y-1">
            <p>
              <span className="text-zinc-400 font-medium">Coût de hedge (perp short BTC) :</span>{' '}
              funding positif = tu <span className="text-emerald-400">reçois</span> du funding en
              shortant le perp. Funding négatif = tu <span className="text-red-400">paies</span>.
            </p>
            <p>
              Moyenne sur {days}j : <span className={rateColor(s.avg)}>{fmt(s.avg, 2)}% ann.</span>
              {s.avg >= 0
                ? ' — le hedge est gratuit en moyenne, et génère même du revenu.'
                : " — le hedge coûte en moyenne, à déduire du spread d'arb."}
            </p>
          </div>

          {/* ── Chart ann. rate ── */}
          <div className="rounded border border-zinc-800 bg-zinc-900/20 p-3">
            <p className="text-[10px] text-zinc-600 mb-2 uppercase tracking-wider">
              Taux annualisé (% / an) · {data.length} périodes de 8h
            </p>
            <LineChart data={data} height={180} />
          </div>

          {/* ── Chart index price ── */}
          <div className="rounded border border-zinc-800 bg-zinc-900/20 p-3">
            <p className="text-[10px] text-zinc-600 mb-2 uppercase tracking-wider">
              Prix index (USD)
            </p>
            <IndexChart data={data} height={120} />
          </div>
        </>
      )}
    </div>
  )
}

/* ── Chart prix index ── */
function IndexChart({ data, height = 120 }: { data: FundingPoint[]; height?: number }) {
  const W = 900
  const H = height
  const PAD = { top: 8, right: 8, bottom: 20, left: 70 }
  const inner = { w: W - PAD.left - PAD.right, h: H - PAD.top - PAD.bottom }

  const prices = data.map((d) => d.index_price)
  const minP = Math.min(...prices)
  const maxP = Math.max(...prices)
  const rangeP = maxP - minP || 1

  const xs = data.map((_, i) => PAD.left + (i / Math.max(data.length - 1, 1)) * inner.w)
  const ys = data.map((d) => PAD.top + (1 - (d.index_price - minP) / rangeP) * inner.h)
  const points = xs.map((x, i) => `${x},${ys[i]}`).join(' ')

  const ticks = [0, 0.5, 1].map((frac) => ({
    val: minP + frac * rangeP,
    y: PAD.top + (1 - frac) * inner.h,
  }))

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height }}>
      {ticks.map(({ val, y }, i) => (
        <g key={i}>
          <line x1={PAD.left - 4} y1={y} x2={PAD.left} y2={y} stroke="#52525b" strokeWidth={1} />
          <text x={PAD.left - 6} y={y + 4} textAnchor="end" fontSize={9} fill="#71717a">
            ${(val / 1000).toFixed(1)}k
          </text>
        </g>
      ))}

      <polyline points={points} fill="none" stroke="#a78bfa" strokeWidth={1.5} />
      <line
        x1={PAD.left}
        y1={PAD.top}
        x2={PAD.left}
        y2={PAD.top + inner.h}
        stroke="#3f3f46"
        strokeWidth={1}
      />
      <line
        x1={PAD.left}
        y1={PAD.top + inner.h}
        x2={PAD.left + inner.w}
        y2={PAD.top + inner.h}
        stroke="#3f3f46"
        strokeWidth={1}
      />
    </svg>
  )
}
