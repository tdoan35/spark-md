import { useCallback, useEffect, useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { connectSse, type SseStatus } from "./sse"
import type { SseEventType } from "./types"

export interface SseContext {
  status: SseStatus
  subscribe: (l: (t: SseEventType, d: unknown) => void) => () => void
}

/** Mount once (above the router). Returns status + a transient-event subscription. */
export function useSse(): SseContext {
  const qc = useQueryClient()
  const [status, setStatus] = useState<SseStatus>("connecting")
  const [listeners] = useState(() => new Set<(t: SseEventType, d: unknown) => void>())

  useEffect(() => connectSse(qc, (t, d) => listeners.forEach((l) => l(t, d)), setStatus), [qc, listeners])

  const subscribe = useCallback(
    (l: (t: SseEventType, d: unknown) => void) => {
      listeners.add(l)
      return () => {
        listeners.delete(l)
      }
    },
    [listeners],
  )
  return { status, subscribe }
}
