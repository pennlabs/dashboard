export function VersionLink({
  version,
  repoName,
}: {
  version: string
  repoName: string
}) {
  if (!version) return <span style={{ color: "var(--text-muted)" }}>—</span>
  return (
    <a
      href={`https://github.com/pennlabs/${repoName}/commit/${version}`}
      target="_blank"
      rel="noreferrer"
      className="mono"
      style={{
        fontSize: 13,
        padding: "2px 8px",
        borderRadius: 6,
        background: "var(--surface-2)",
        border: "1px solid var(--border)",
        color: "var(--text)",
        textDecoration: "none",
      }}
    >
      {version.slice(0, 7)}
    </a>
  )
}
