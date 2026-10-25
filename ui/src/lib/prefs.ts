// localStorage-backed UI preferences (theme, inspector, chat width). Session-memory is fine
// for everything else.
import { useEffect, useState } from "react"

export function readPref<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key)
    return raw == null ? fallback : (JSON.parse(raw) as T)
  } catch {
    return fallback
  }
}

export function writePref<T>(key: string, value: T) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    /* localStorage full or blocked: preference simply does not persist */
  }
}

/** Rename the former demo preference without changing custom names or signed records. */
export function readApprover(): string {
  const saved = localStorage.getItem("sparkmd-approver")
  const fallback = "Dr. Spark (demo)"
  if (saved === "Dr. Joyce (demo)") {
    localStorage.setItem("sparkmd-approver", fallback)
    return fallback
  }
  return saved ?? fallback
}

export function usePref<T>(key: string, initial: T) {
  const [v, setV] = useState<T>(() => readPref(key, initial))
  useEffect(() => writePref(key, v), [key, v])
  return [v, setV] as const
}
