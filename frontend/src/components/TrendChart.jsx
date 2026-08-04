import { useState } from 'react'

const WIDTH = 640
const HEIGHT = 240
const PADDING_X = 32
const PADDING_TOP = 26
const PADDING_BOTTOM = 32

export function TrendChart({ xLabels, series }) {
  const [hoveredIndex, setHoveredIndex] = useState(null)

  const plotWidth = WIDTH - PADDING_X * 2
  const plotHeight = HEIGHT - PADDING_TOP - PADDING_BOTTOM
  const stepX = xLabels.length > 1 ? plotWidth / (xLabels.length - 1) : 0
  const baseY = HEIGHT - PADDING_BOTTOM

  function xFor(i) {
    return PADDING_X + i * stepX
  }

  function yFor(v, maxVal) {
    return baseY - (v / maxVal) * plotHeight
  }

  const tooltipWidth = 130
  const tooltipHeight = 14 * (series.length + 1) + 10

  return (
    <div>
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="w-full h-60">
        <line x1={PADDING_X} y1={baseY} x2={WIDTH - PADDING_X} y2={baseY} stroke="#e5e7eb" />

        {series.map((s) => {
          const maxVal = Math.max(1, ...s.values)
          return (
            <polyline
              key={s.label}
              points={s.values.map((v, i) => `${xFor(i)},${yFor(v, maxVal)}`).join(' ')}
              fill="none"
              stroke={s.color}
              strokeWidth="2.5"
            />
          )
        })}

        {series.map((s) => {
          const maxVal = Math.max(1, ...s.values)
          return s.values.map((v, i) => (
            <circle key={`${s.label}-${i}`} cx={xFor(i)} cy={yFor(v, maxVal)} r="3.5" fill={s.color} pointerEvents="none" />
          ))
        })}

        {xLabels.map((label, i) => (
          <text key={label} x={xFor(i)} y={HEIGHT - 10} fontSize="9" textAnchor="middle" fill="#9ca3af">
            {label}
          </text>
        ))}

        {hoveredIndex !== null && (
          <g pointerEvents="none">
            <line x1={xFor(hoveredIndex)} y1={PADDING_TOP} x2={xFor(hoveredIndex)} y2={baseY} stroke="#d1d5db" strokeDasharray="3 3" />
            {series.map((s) => {
              const maxVal = Math.max(1, ...s.values)
              const y = yFor(s.values[hoveredIndex], maxVal)
              return <circle key={`hi-${s.label}`} cx={xFor(hoveredIndex)} cy={y} r="5.5" fill="white" stroke={s.color} strokeWidth="2" />
            })}

            {(() => {
              const rawX = xFor(hoveredIndex) - tooltipWidth / 2
              const x = Math.min(Math.max(rawX, PADDING_X - 10), WIDTH - PADDING_X + 10 - tooltipWidth)
              const y = 2
              return (
                <g>
                  <rect x={x} y={y} width={tooltipWidth} height={tooltipHeight} rx="4" fill="white" stroke="#e5e7eb" />
                  <text x={x + 8} y={y + 14} fontSize="9" fill="#6b7280">{xLabels[hoveredIndex]}</text>
                  {series.map((s, si) => (
                    <text key={s.label} x={x + 8} y={y + 14 + 14 * (si + 1)} fontSize="9" fill={s.color}>
                      {s.label}: {s.prefix || ''}{s.values[hoveredIndex]}
                    </text>
                  ))}
                </g>
              )
            })()}
          </g>
        )}

        {xLabels.map((_, i) => {
          const left = i === 0 ? PADDING_X : xFor(i) - stepX / 2
          const right = i === xLabels.length - 1 ? WIDTH - PADDING_X : xFor(i) + stepX / 2
          return (
            <rect
              key={`hit-${i}`}
              x={left}
              y={PADDING_TOP}
              width={right - left}
              height={plotHeight}
              fill="transparent"
              onMouseEnter={() => setHoveredIndex(i)}
              onMouseLeave={() => setHoveredIndex(null)}
            />
          )
        })}
      </svg>

      <div className="flex gap-4 justify-center mt-2">
        {series.map((s) => (
          <div key={s.label} className="flex items-center gap-1.5 text-xs text-text-secondary">
            <span className="inline-block w-2.5 h-2.5 rounded-full" style={{ backgroundColor: s.color }} />
            {s.label}
          </div>
        ))}
      </div>
    </div>
  )
}
