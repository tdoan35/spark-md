/** Formats worker numbers. The UI formats only; it never computes a measurement, growth or category. */
export const mm = (v: number | null | undefined, digits = 1) => (v == null ? "—" : `${v.toFixed(digits)} mm`)
export const mmNum = (v: number | null | undefined, digits = 1) => (v == null ? "—" : v.toFixed(digits))
export const pct = (v: number | null | undefined) => (v == null ? "—" : `${v.toFixed(1)} %`)
export const hu = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v)} HU`)
export const days = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v)} d`)
export const signed = (v: number | null | undefined, unit = "mm") => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(1)} ${unit}`)

export function dayLabel(offset: number | null | undefined) {
  return offset == null ? "Day —" : `Day ${offset}`
}

export function hm(iso: string | null | undefined) {
  if (!iso) return "—"
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
}

export function relTime(iso: string | null | undefined) {
  if (!iso) return ""
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return ""
  const s = Math.max(0, Math.round((Date.now() - t) / 1000))
  if (s < 45) return "just now"
  if (s < 3600) return `${Math.round(s / 60)} min ago`
  if (s < 86400) return `${Math.round(s / 3600)} h ago`
  return `${Math.round(s / 86400)} d ago`
}

export function bytes(n: number | null | undefined) {
  if (n == null) return "—"
  if (n < 1000) return `${n} B`
  if (n < 1e6) return `${(n / 1e3).toFixed(1)} kB`
  if (n < 1e9) return `${(n / 1e6).toFixed(2)} MB`
  return `${(n / 1e9).toFixed(2)} GB`
}

export function shortId(uid: string) {
  const m = uid.match(/(\d{6})-([TN]\d)$/)
  if (m) return `${m[2]}`
  return uid.split(".").pop() ?? uid
}

export const STATUS_LABEL: Record<string, string> = {
  received: "Received",
  organized: "Loading files",
  analyzing: "Analyzing",
  awaiting_confirmation: "Awaiting Review",
  analyzed: "Analyzed",
  reported: "Awaiting approval",
  approved: "Approved",
  failed: "Failed",
}

export const PRIORITY_LABEL: Record<string, string> = {
  routine: "Routine",
  elevated: "Elevated",
  urgent: "Urgent",
}

/** Lung-RADS badge colour = urgency of management, not a diagnosis (08). */
export function lungRadsClass(lr: string | null | undefined) {
  if (!lr) return "bg-muted text-muted-foreground"
  if (lr === "0") return "bg-muted text-muted-foreground"
  if (lr === "1" || lr === "2") return "bg-ok-soft text-ok"
  if (lr === "3") return "bg-warn-soft text-warn"
  if (lr === "4A") return "bg-warn text-white dark:text-warn-soft"
  if (lr === "4B" || lr === "4X") return "bg-alert text-white dark:text-alert-soft"
  return "bg-muted text-muted-foreground"
}
