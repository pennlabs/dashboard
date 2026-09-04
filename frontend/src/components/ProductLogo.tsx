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

// Products whose logo file isn't named after the k8s `part-of` label. Keys are
// normalized (lowercase, non-alphanumerics collapsed to hyphens), so the
// aliases below cover the label spellings we see in the wild.
const LOGO_OVERRIDES: Record<string, string> = {
  // The penn-courses monorepo ships as one product; PCR's mark stands in for it.
  "penn-courses": "/logos/pcr-logo.svg",
  "penn-course-review": "/logos/pcr-logo.svg",
  pcr: "/logos/pcr-logo.svg",
  "penn-course-plan": "/logos/pcp-logo.svg",
  pcp: "/logos/pcp-logo.svg",
  "penn-mobile": "/logos/penn-mobile-logo.svg",
  pennmobile: "/logos/penn-mobile-logo.svg",
  "penn-clubs": "/logos/clubs-logo.svg",
  "office-hours-queue": "/logos/ohq-logo.svg",
  ohq: "/logos/ohq-logo.svg",
}

function normalize(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
}

export default function ProductLogo({ name, displayName, size = 44 }: Props) {
  const [extIndex, setExtIndex] = useState(0)
  const [failed, setFailed] = useState(false)

  const override =
    LOGO_OVERRIDES[normalize(name)] ?? LOGO_OVERRIDES[normalize(displayName)]
  const src = override ?? `/logos/${name}.${EXTENSIONS[extIndex]}`

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
            // An override names one exact file -- there's nothing else to try.
            if (!override && extIndex < EXTENSIONS.length - 1) {
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
