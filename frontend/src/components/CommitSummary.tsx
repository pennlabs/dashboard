import type { CSSProperties } from "react"

import type { CommitInfo } from "../types"

/** Renders nothing when GitHub couldn't describe the commit: the SHA still stands. */
export default function CommitSummary({
  commit,
  style,
}: {
  commit?: CommitInfo
  style?: CSSProperties
}) {
  if (!commit) return null
  return (
    <span
      style={{
        fontSize: 13,
        color: "var(--text-secondary)",
        minWidth: 0,
        overflowWrap: "anywhere",
        ...style,
      }}
    >
      {commit.message}
      {commit.author ? <span className="muted"> · {commit.author}</span> : null}
    </span>
  )
}
