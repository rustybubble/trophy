/** m:ss for a duration in seconds ("—" when unknown), like tv-core's fmtDuration. */
export function fmtDuration(s?: number | null): string {
  if (s == null || !Number.isFinite(s)) return "—";
  const t = Math.max(0, s);
  return `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, "0")}`;
}
