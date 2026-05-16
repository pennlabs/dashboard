import { useState } from "react"

interface Props {
  name: string
  displayName: string
  size?: number
}

function initials(value: string): string {
  const parts = value
    .replace(/[-_]/g, " ")
    .split(/\s+/)
    .filter(Boolean)
  if (parts.length === 0) return "?"
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[1][0]).toUpperCase()
}

// Tries /logos/<name>.png, then .svg, then .jpg, before falling back to
// initials. The user drops files into frontend/public/logos to wire each
// product up.
const EXTENSIONS = ["png", "svg", "jpg", "jpeg", "webp"] as const

export default function ProductLogo({ name, displayName, size = 44 }: Props) {
  const [extIndex, setExtIndex] = useState(0)
  const [failed, setFailed] = useState(false)

  const src = `/logos/${name}.${EXTENSIONS[extIndex]}`

  return (
    <span
      className="product-logo"
      style={{ width: size, height: size, fontSize: size * 0.36 }}
      aria-hidden="true"
    >
      {failed ? (
        initials(displayName || name)
      ) : (
        <img
          key={src}
          src={src}
          alt=""
          onError={() => {
            if (extIndex < EXTENSIONS.length - 1) {
              setExtIndex(extIndex + 1)
            } else {
              setFailed(true)
            }
          }}
        />
      )}
    </span>
  )
}
