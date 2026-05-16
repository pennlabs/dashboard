import { useState } from "react"

import type { ReplicaSetSnapshot } from "../types"

interface Props {
  replicasets: ReplicaSetSnapshot[]
  onConfirm: (image: string) => void
  onClose: () => void
  isLoading: boolean
}

export default function RollbackDialog({
  replicasets,
  onConfirm,
  onClose,
  isLoading,
}: Props) {
  // Default to the second-newest revision (i.e. the previous version), which
  // is the most common rollback target.
  const [selectedImage, setSelectedImage] = useState(
    replicasets[1]?.image ?? replicasets[0]?.image ?? ""
  )

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
              Rev {rs.revision} · {rs.version ? rs.version.slice(0, 7) : "?"}{" "}
              ·{" "}
              {rs.created_at
                ? new Date(rs.created_at).toLocaleDateString()
                : "?"}
            </option>
          ))}
        </select>
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
