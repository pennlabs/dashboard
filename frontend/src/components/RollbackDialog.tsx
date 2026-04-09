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
  const [selectedImage, setSelectedImage] = useState(
    replicasets[1]?.image ?? replicasets[0]?.image ?? ""
  )

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.5)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
      }}
    >
      <div
        style={{
          background: "white",
          padding: 24,
          borderRadius: 8,
          minWidth: 400,
          display: "grid",
          gap: 16,
        }}
      >
        <h3 style={{ margin: 0 }}>Select version to roll back to</h3>
        <select
          value={selectedImage}
          onChange={(e) => setSelectedImage(e.target.value)}
          style={{ padding: 8, border: "1px solid #d1d5db", borderRadius: 6 }}
        >
          {replicasets.map((rs) => (
            <option key={rs.id} value={rs.image}>
              Rev {rs.revision} - {rs.version.slice(0, 7)} -{" "}
              {new Date(rs.created_at).toLocaleDateString()}
            </option>
          ))}
        </select>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <button type="button" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            onClick={() => onConfirm(selectedImage)}
            style={{
              background: "#ef4444",
              color: "white",
              border: "none",
              borderRadius: 4,
              padding: "8px 12px",
            }}
            disabled={isLoading}
          >
            Confirm
          </button>
        </div>
      </div>
    </div>
  )
}
