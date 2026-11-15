import { useEffect, useRef, useState } from "react"
import type { KeyboardEvent, PointerEvent } from "react"

import type { LoadPoint } from "../types"

const HEIGHT = 240
const MARGIN = { top: 14, right: 16, bottom: 26, left: 36 }

const WINDOW_LONGER_THAN_A_DAY = 24 * 60 * 60 * 1000

interface Props {
  points: LoadPoint[]
  vcpus: number
}

/** Tick spacing that gives about four clean values: 1, 2, 5, 10, 20, 50... */
function tickStep(max: number): number {
  const magnitude = 10 ** Math.floor(Math.log10(max / 4))
  const nice = [1, 2, 5, 10].find((m) => m * magnitude >= max / 4) ?? 10
  return nice * magnitude
}

function formatTime(iso: string, withDate: boolean): string {
  const date = new Date(iso)
  const time = date.toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone: "UTC",
  })
  if (!withDate) return time
  const day = date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  })
  return `${day} ${time}`
}

/** Path data for each unbroken run of samples, so a gap stays a gap. */
function runsOf(
  points: LoadPoint[],
  x: (index: number) => number,
  y: (load: number) => number
): { line: string; area: string }[] {
  const runs: { line: string; area: string }[] = []
  let run: [number, number][] = []

  const flush = () => {
    if (run.length > 1) {
      const line = run.map(([px, py]) => `${px},${py}`).join(" L")
      runs.push({
        line: `M${line}`,
        area: `M${run[0][0]},${y(0)} L${line} L${run[run.length - 1][0]},${y(0)} Z`,
      })
    }
    run = []
  }

  points.forEach((point, index) => {
    if (point.load === null) flush()
    else run.push([x(index), y(point.load)])
  })
  flush()
  return runs
}

/** Database load over time, with a line at the CPU count it can actually run. */
export default function LoadChart({ points, vcpus }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(0)
  const [active, setActive] = useState<number | null>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const observer = new ResizeObserver(([entry]) =>
      setWidth(entry.contentRect.width)
    )
    observer.observe(container)
    return () => observer.disconnect()
  }, [])

  const values = points.flatMap((p) => (p.load === null ? [] : [p.load]))
  const step = tickStep(Math.max(...values, vcpus) * 1.1)
  const yMax = Math.ceil((Math.max(...values, vcpus) * 1.1) / step) * step
  const ticks = Array.from(
    { length: Math.round(yMax / step) + 1 },
    (_, i) => i * step
  )

  const plotWidth = Math.max(width - MARGIN.left - MARGIN.right, 0)
  const plotHeight = HEIGHT - MARGIN.top - MARGIN.bottom
  const x = (index: number) =>
    MARGIN.left + (index / Math.max(points.length - 1, 1)) * plotWidth
  const y = (load: number) => MARGIN.top + (1 - load / yMax) * plotHeight

  const spansDays =
    points.length > 1 &&
    new Date(points[points.length - 1].time).getTime() -
      new Date(points[0].time).getTime() >
      WINDOW_LONGER_THAN_A_DAY

  const labelCount = Math.max(Math.min(Math.floor(plotWidth / 110), 6), 2)
  const labelIndexes = Array.from({ length: labelCount }, (_, i) =>
    Math.round((i / (labelCount - 1)) * (points.length - 1))
  )

  const onPointerMove = (event: PointerEvent<SVGRectElement>) => {
    const left = event.currentTarget.getBoundingClientRect().left
    const fraction = (event.clientX - left) / Math.max(plotWidth, 1)
    setActive(Math.round(fraction * (points.length - 1)))
  }

  const onKeyDown = (event: KeyboardEvent<SVGSVGElement>) => {
    const move = { ArrowLeft: -1, ArrowRight: 1 }[event.key]
    if (!move) return
    event.preventDefault()
    setActive((current) =>
      Math.min(
        Math.max((current ?? points.length) + move, 0),
        points.length - 1
      )
    )
  }

  const activePoint = active === null ? undefined : points[active]

  return (
    <div className="load-chart" ref={containerRef}>
      {width > 0 && (
        <svg
          width={width}
          height={HEIGHT}
          role="img"
          aria-label={`Database load over time, peaking at ${Math.max(
            ...values
          ).toFixed(1)} active sessions against ${vcpus} vCPUs.`}
          tabIndex={0}
          onKeyDown={onKeyDown}
          onBlur={() => setActive(null)}
        >
          {ticks.map((tick) => (
            <g key={tick}>
              <line
                className="load-chart-grid"
                x1={MARGIN.left}
                x2={MARGIN.left + plotWidth}
                y1={y(tick)}
                y2={y(tick)}
              />
              <text
                className="load-chart-label"
                x={MARGIN.left - 8}
                y={y(tick)}
                dy="0.32em"
                textAnchor="end"
              >
                {tick}
              </text>
            </g>
          ))}

          {labelIndexes.map((index, i) => (
            <text
              key={index}
              className="load-chart-label"
              x={x(index)}
              y={HEIGHT - 6}
              textAnchor={
                i === 0 ? "start" : i === labelCount - 1 ? "end" : "middle"
              }
            >
              {formatTime(points[index].time, spansDays)}
            </text>
          ))}

          {runsOf(points, x, y).map((run) => (
            <g key={run.line}>
              <path className="load-chart-area" d={run.area} />
              <path className="load-chart-line" d={run.line} />
            </g>
          ))}

          <line
            className="load-chart-limit"
            x1={MARGIN.left}
            x2={MARGIN.left + plotWidth}
            y1={y(vcpus)}
            y2={y(vcpus)}
          />
          <text
            className="load-chart-limit-label"
            x={MARGIN.left + 6}
            y={y(vcpus) - 6}
          >
            {vcpus} vCPUs
          </text>

          {active !== null && activePoint && (
            <g>
              <line
                className="load-chart-crosshair"
                x1={x(active)}
                x2={x(active)}
                y1={MARGIN.top}
                y2={MARGIN.top + plotHeight}
              />
              {activePoint.load !== null && (
                <circle
                  className="load-chart-dot"
                  cx={x(active)}
                  cy={y(activePoint.load)}
                  r={4}
                />
              )}
            </g>
          )}

          <rect
            x={MARGIN.left}
            y={MARGIN.top}
            width={plotWidth}
            height={plotHeight}
            fill="transparent"
            onPointerMove={onPointerMove}
            onPointerLeave={() => setActive(null)}
          />
        </svg>
      )}

      {active !== null && activePoint && (
        <div
          className="load-chart-tooltip"
          style={{
            left: x(active),
            top: MARGIN.top,
            transform: `translateX(${
              x(active) > width / 2 ? "calc(-100% - 10px)" : "10px"
            })`,
          }}
        >
          <strong>
            {activePoint.load === null ? "No data" : activePoint.load.toFixed(1)}
          </strong>
          {activePoint.load !== null && <span> active sessions</span>}
          <div className="muted">
            {formatTime(activePoint.time, true)} UTC
          </div>
        </div>
      )}
    </div>
  )
}
