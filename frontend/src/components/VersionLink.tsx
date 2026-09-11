// A commit SHA is hex and at least 7 characters. Kittyhawk tags product images
// with the full 40-character SHA, but not every version label in the cluster is
// one: `pingmobile-backend` is labelled `latest`, for instance. Linking those to
// /commit/<value> just produces a 404, so we render them as plain text instead.
const COMMIT_RE = /^[0-9a-f]{7,40}$/

const chipStyle = {
  fontSize: 13,
  padding: "2px 8px",
  borderRadius: 6,
  background: "var(--surface-2)",
  border: "1px solid var(--border)",
  color: "var(--text)",
  textDecoration: "none",
} as const

export function VersionLink({
  version,
  repoName,
}: {
  version: string
  repoName: string
}) {
  if (!version) return <span style={{ color: "var(--text-muted)" }}>—</span>

  // Not a commit -> show the value, but don't pretend it's a linkable revision.
  if (!COMMIT_RE.test(version)) {
    return (
      <span className="mono" style={chipStyle} title="Not a commit reference">
        {version}
      </span>
    )
  }

  return (
    <a
      href={`https://github.com/pennlabs/${repoName}/commit/${version}`}
      target="_blank"
      rel="noreferrer"
      className="mono"
      style={chipStyle}
    >
      {version.slice(0, 7)}
    </a>
  )
}
