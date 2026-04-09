export function VersionLink({
  version,
  repoName,
}: {
  version: string
  repoName: string
}) {
  if (!version) return <span style={{ color: "#9ca3af" }}>-</span>
  return (
    <a
      href={`https://github.com/pennlabs/${repoName}/commit/${version}`}
      target="_blank"
      rel="noreferrer"
      style={{ fontFamily: "monospace", fontSize: "13px" }}
    >
      {version.slice(0, 7)}
    </a>
  )
}
