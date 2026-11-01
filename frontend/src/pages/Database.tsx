import { useState } from "react"
import type { FormEvent } from "react"
import { useSearchParams } from "react-router-dom"

import { ApiError } from "../api"
import LoadChart from "../components/LoadChart"
import { useDatabaseInsights } from "../hooks/useDatabaseInsights"
import type { DatabaseInsights, LoadShare, TopQuery } from "../types"

const MINUTE = 60 * 1000
const HOUR = 60 * MINUTE

const PRESETS = [
  { label: "1 hour", ms: HOUR },
  { label: "6 hours", ms: 6 * HOUR },
  { label: "24 hours", ms: 24 * HOUR },
  { label: "7 days", ms: 7 * 24 * HOUR },
]

// How much to show around an alarm's time: enough before it to see the spike
// start, and more after, because spikes tend to outlast the first alarm.
const BEFORE_ALARM = 15 * MINUTE
const AFTER_ALARM = 30 * MINUTE

// Performance Insights cuts query text off at this length.
const STATEMENT_LIMIT = 500

const MONTHS = [
  "january",
  "february",
  "march",
  "april",
  "may",
  "june",
  "july",
  "august",
  "september",
  "october",
  "november",
  "december",
]

/**
 * The moment an alarm is about, from a pasted timestamp or a whole alarm email.
 *
 * The email's datapoint time, `(01/11/26 20:17:00)`, comes first because it says
 * when the problem was, whereas the "Timestamp:" line is when the alarm fired
 * minutes later. Both are UTC, and the datapoint is day/month/year.
 */
export function parseAlarmTime(text: string): Date | null {
  const datapoint = text.match(
    /(\d{2})\/(\d{2})\/(\d{2})\s+(\d{2}):(\d{2}):(\d{2})/
  )
  if (datapoint) {
    const [, day, month, year, hour, minute, second] = datapoint.map(Number)
    return new Date(
      Date.UTC(2000 + year, month - 1, day, hour, minute, second)
    )
  }

  const written = text.match(
    /(\d{1,2})\s+([A-Za-z]+),?\s+(\d{4})\s+(\d{2}):(\d{2}):(\d{2})/
  )
  const month = written ? MONTHS.indexOf(written[2].toLowerCase()) : -1
  if (written && month >= 0) {
    return new Date(
      Date.UTC(
        Number(written[3]),
        month,
        Number(written[1]),
        Number(written[4]),
        Number(written[5]),
        Number(written[6])
      )
    )
  }

  // Anything else is a plain date and time. UTC unless it says otherwise, like
  // everything else on this page.
  const trimmed = text.trim().replace(" ", "T")
  const hasZone = /(Z|[+-]\d{2}:?\d{2})$/i.test(trimmed)
  const parsed = new Date(hasZone ? trimmed : `${trimmed}Z`)
  return Number.isNaN(parsed.getTime()) ? null : parsed
}

function lastPeriod(ms: number) {
  const end = new Date()
  return {
    start: new Date(end.getTime() - ms).toISOString(),
    end: end.toISOString(),
  }
}

function formatUtc(iso: string): string {
  return `${new Date(iso).toISOString().slice(0, 16).replace("T", " ")} UTC`
}

function percent(share: number): string {
  return share < 0.01 ? "<1%" : `${Math.round(share * 100)}%`
}

export default function Database() {
  const [params, setParams] = useSearchParams()
  const [fallback] = useState(() => lastPeriod(HOUR))
  const [alarmText, setAlarmText] = useState("")
  const [alarmError, setAlarmError] = useState(false)

  // The window lives in the URL so a link to a spike can be shared.
  const start = params.get("start") ?? fallback.start
  const end = params.get("end") ?? fallback.end
  const [activePreset, setActivePreset] = useState<string | null>(
    params.has("start") ? null : PRESETS[0].label
  )

  const { data, isLoading, error } = useDatabaseInsights(start, end)

  const showPreset = (label: string, ms: number) => {
    setActivePreset(label)
    setParams(lastPeriod(ms))
  }

  const showAlarm = (event: FormEvent) => {
    event.preventDefault()
    const moment = parseAlarmTime(alarmText)
    setAlarmError(!moment)
    if (!moment) return
    setActivePreset(null)
    setParams({
      start: new Date(moment.getTime() - BEFORE_ALARM).toISOString(),
      end: new Date(moment.getTime() + AFTER_ALARM).toISOString(),
    })
  }

  return (
    <div className="page">
      <div style={{ marginBottom: 18 }}>
        <h1 style={{ margin: 0, fontSize: 26, fontWeight: 700 }}>Database</h1>
        <p
          style={{
            margin: "6px 0 0",
            color: "var(--text-secondary)",
            fontSize: 14,
          }}
        >
          What the shared production database was doing, from AWS Performance
          Insights. All times are UTC.
        </p>
      </div>

      <div className="toolbar">
        <form className="alarm-form" onSubmit={showAlarm}>
          <input
            className="select"
            aria-label="Alarm email or time"
            placeholder="Paste an alarm email or a time, e.g. 2026-11-01 20:17"
            value={alarmText}
            onChange={(e) => {
              setAlarmText(e.target.value)
              setAlarmError(false)
            }}
            aria-invalid={alarmError}
          />
          <button type="submit" className="btn btn-primary">
            Show
          </button>
        </form>
        <div className="filter-group" role="group" aria-label="Time range">
          {PRESETS.map((preset) => (
            <button
              key={preset.label}
              type="button"
              className="filter-pill"
              aria-pressed={activePreset === preset.label}
              onClick={() => showPreset(preset.label, preset.ms)}
            >
              {preset.label}
            </button>
          ))}
        </div>
      </div>

      {alarmError && (
        <p className="alarm-error" role="alert">
          Couldn't find a time in that. Try something like 2026-11-01 20:17.
        </p>
      )}

      {isLoading && <div className="skeleton" style={{ height: 320 }} />}
      {error && <InsightsError error={error} />}
      {data && <Insights data={data} />}
    </div>
  )
}

function InsightsError({ error }: { error: unknown }) {
  const status = error instanceof ApiError ? error.status : undefined
  const message =
    status === 503
      ? "This backend can't reach AWS Performance Insights right now. Locally, start it with AWS_PROFILE=pennlabs."
      : status === 400
        ? "That time range can't be shown. It can be up to 14 days long, within the history AWS keeps."
        : (error as Error).message

  return (
    <div className="card" style={{ padding: 20 }}>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>
        Couldn't load database activity
      </div>
      <p className="muted" style={{ margin: 0, fontSize: 14 }}>
        {message}
      </p>
    </div>
  )
}

function Insights({ data }: { data: DatabaseInsights }) {
  if (!data.load.some((point) => point.load !== null)) {
    return (
      <div className="card" style={{ padding: 20 }}>
        No activity was recorded between {formatUtc(data.start)} and{" "}
        {formatUtc(data.end)}.
      </div>
    )
  }

  return (
    <div className="db-sections">
      <section className="card db-card">
        <div className="db-card-header">
          <div>
            <h2>Load</h2>
            <p className="muted">
              {formatUtc(data.start)} to {formatUtc(data.end)}. Above the{" "}
              {data.vcpus} vCPU line, queries are waiting for CPU.
            </p>
          </div>
          <dl className="db-stats">
            <div>
              <dt>Peak</dt>
              <dd>{data.peak_load.toFixed(1)}</dd>
            </div>
            <div>
              <dt>Average</dt>
              <dd>{data.average_load.toFixed(1)}</dd>
            </div>
          </dl>
        </div>
        <LoadChart points={data.load} vcpus={data.vcpus} />
        <details className="db-table-toggle">
          <summary>Show as a table</summary>
          <table className="db-table">
            <thead>
              <tr>
                <th>Time (UTC)</th>
                <th className="db-number">Active sessions</th>
              </tr>
            </thead>
            <tbody>
              {data.load.map((point) => (
                <tr key={point.time}>
                  <td>{formatUtc(point.time).replace(" UTC", "")}</td>
                  <td className="db-number">
                    {point.load === null ? "No data" : point.load.toFixed(1)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      </section>

      <section className="card db-card">
        <h2>Top queries</h2>
        <p className="muted">
          Query text can include real values, so don't share it outside Labs.
        </p>
        {data.queries.length === 0 ? (
          <p className="muted">No queries were sampled in this window.</p>
        ) : (
          <ol className="db-queries">
            {data.queries.map((query) => (
              <Query key={query.id} query={query} />
            ))}
          </ol>
        )}
      </section>

      <div className="db-columns">
        <Shares title="By database user" rows={data.users} />
        <Shares title="By wait event" rows={data.waits} />
      </div>
    </div>
  )
}

function Query({ query }: { query: TopQuery }) {
  return (
    <li>
      <span className="db-share">{percent(query.share)}</span>
      <details>
        <summary className="mono">{query.statement}</summary>
        <pre className="mono">{query.statement}</pre>
        <p className="muted">
          ID {query.id}
          {query.statement.length >= STATEMENT_LIMIT &&
            ". Performance Insights cuts query text off at 500 characters."}
        </p>
      </details>
    </li>
  )
}

function Shares({ title, rows }: { title: string; rows: LoadShare[] }) {
  return (
    <section className="card db-card">
      <h2>{title}</h2>
      {rows.length === 0 ? (
        <p className="muted">Nothing was sampled in this window.</p>
      ) : (
        <table className="db-table">
          <tbody>
            {rows.map((row) => (
              <tr key={row.name}>
                <td>{row.name}</td>
                <td className="db-number">{percent(row.share)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}
