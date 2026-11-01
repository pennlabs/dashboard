import { useState } from "react"

import type { Commits, ReplicaSetSnapshot } from "../types"
import { revisionLabel } from "./CompareRevisions"
import { compareUrl } from "./VersionLink"

interface Props {
  replicasets: ReplicaSetSnapshot[]
  commits?: Commits
  currentVersion: string
  repoName: string
  onConfirm: (image: string) => void
  onClose: () => void
  isLoading: boolean
}

export default function RollbackDialog({
  replicasets,
  commits,
  currentVersion,
  repoName,
  onConfirm,
  onClose,
  isLoading,
}: Props) {
  // Default to the second-newest revision (i.e. the previous version), which
  // is the most common rollback target.
  const [selectedImage, setSelectedImage] = useState(
    replicasets[1]?.image ?? replicasets[0]?.image ?? ""
  )

  // Target to current, so the diff reads as what rolling back would take away.
  const target = replicasets.find((rs) => rs.image === selectedImage)
  const diffUrl = target
    ? compareUrl(repoName, target.version, currentVersion)
    : null

  return (
    <div
      role="dialog"
      aria-modal="true"
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.55)",
        backdropFilter: "blur(4px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
        padding: 16,
      }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "var(--surface)",
          padding: 24,
          borderRadius: 14,
          minWidth: 420,
          maxWidth: "100%",
          display: "grid",
          gridTemplateColumns: "minmax(0, 1fr)",
          gap: 18,
          border: "1px solid var(--border)",
          boxShadow: "var(--shadow-lg)",
        }}
      >
        <div>
          <h3 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>
            Roll back deployment
          </h3>
          <p
            style={{
              margin: "6px 0 0",
              color: "var(--text-secondary)",
              fontSize: 13,
            }}
          >
            Select a previous revision to redeploy.
          </p>
        </div>
        <select
          className="select"
          value={selectedImage}
          onChange={(e) => setSelectedImage(e.target.value)}
        >
          {replicasets.map((rs) => (
            <option key={rs.revision} value={rs.image}>
              {revisionLabel(rs, commits?.[rs.version])}
            </option>
          ))}
        </select>
        {diffUrl ? (
          <a
            href={diffUrl}
            target="_blank"
            rel="noreferrer"
            style={{ fontSize: 13, width: "fit-content" }}
          >
            See what this rolls back on GitHub ↗
          </a>
        ) : null}
        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            gap: 10,
          }}
        >
          <button
            type="button"
            className="btn btn-secondary"
            onClick={onClose}
            disabled={isLoading}
          >
            Cancel
          </button>
          <button
            type="button"
            className="btn btn-danger"
            onClick={() => onConfirm(selectedImage)}
            disabled={isLoading}
          >
            {isLoading ? "Rolling back…" : "Confirm rollback"}
          </button>
        </div>
      </div>
    </div>
  )
}
