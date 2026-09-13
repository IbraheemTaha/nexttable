export function Badge({ status, label }: { status: string; label: string }) {
  return <span className={`badge badge-${status}`}>{label}</span>
}
