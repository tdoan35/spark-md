import { createContext, useContext } from "react"
import type { SseContext } from "@/api/use-sse"
import type { DemoState } from "@/api/types"

export interface AppCtx {
  sse: SseContext
  /** Replay banner: the demo harness's current state, or null when not replaying. */
  demo: DemoState | null
  openStudy: (uid: string) => void
  openWorklistTab: () => void
  closeTab: (id: string) => void
  newTab: () => void
  toggleTheme: () => void
  openSearch: () => void
  go: (path: string) => void
}

export const AppContext = createContext<AppCtx | null>(null)

export function useApp() {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error("useApp outside AppContext")
  return ctx
}
