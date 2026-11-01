import { useState } from "react"

import type { CommitInfo, Commits, ReplicaSetSnapshot } from "../types"
import { compareUrl, isCommit } from "./VersionLink"

const MAX_SUBJECT_LENGTH = 48

/** One line describing a revision, for use inside a <select>. */
export function revisionLabel(rs: ReplicaSetSnapshot, commit?: CommitInfo) {
  const date = rs.created_at ? new Date(rs.created_at).toLocaleDateString() : "?"
  const label = `Rev ${rs.revision} · ${rs.version ? rs.version.slice(0, 7) : "?"} · ${date}`
  if (!commit) return label
  const subject =
    commit.message.length > MAX_SUBJECT_LENGTH
      ? `${commit.message.slice(0, MAX_SUBJECT_LENGTH)}…`
      : commit.message
  return `${label} · ${subject}`
}

interface Props {
  replicasets: ReplicaSetSnapshot[]
  commits?: Commits
  repoName: string
}

export default function CompareRevisions({
  replicasets,
  commits,
  repoName,
}: Props) {
  // Null until the user picks, so the defaults follow new revisions as they roll
  // out rather than freezing on whatever was newest when the page loaded.
  const [from, setFrom] = useState<string | null>(null)
  const [to, setTo] = useState<string | null>(null)

  // Only commits can be compared, and revisions can share one.
  const options = replicasets.filter(
    (rs, i) =>
      isCommit(rs.version) &&
      replicasets.findIndex((other) => other.version === rs.version) === i
  )
  if (options.length < 2) return null

  const base = from ?? options[1].version
  const head = to ?? options[0].version
  const url = compareUrl(repoName, base, head)

  const picker = (
    label: string,
    value: string,
    onChange: (version: string) => void
  ) => (
    <label
      style={{
        display: "grid",
        gap: 4,
        flex: "1 1 240px",
        minWidth: 0,
        fontSize: 12,
        color: "var(--text-secondary)",
      }}
    >
      {label}
      <select
        className="select"
        style={{ width: "100%" }}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map((rs) => (
          <option key={rs.revision} value={rs.version}>
            {revisionLabel(rs, commits?.[rs.version])}
          </option>
        ))}
      </select>
    </label>
  )

  return (
    <div
      className="card"
      style={{
        padding: 12,
        display: "flex",
        alignItems: "flex-end",
        gap: 10,
        flexWrap: "wrap",
      }}
    >
      {picker("From", base, setFrom)}
      {picker("To", head, setTo)}
      {url ? (
        <a
          href={url}
          target="_blank"
          rel="noreferrer"
          className="btn btn-secondary"
        >
          View diff ↗
        </a>
      ) : (
        <span className="muted" style={{ fontSize: 13, padding: "9px 0" }}>
          Same commit
        </span>
      )}
    </div>
  )
}
