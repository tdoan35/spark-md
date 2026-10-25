import { useCallback, useEffect, useState } from "react"
import { usePref } from "@/lib/prefs"

export function useTheme() {
  const [theme, setTheme] = usePref<"light" | "dark">("sparkmd-theme", "light")
  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark")
    document.documentElement.classList.toggle("light", theme !== "dark")
  }, [theme])
  const toggle = useCallback(() => setTheme((t) => (t === "dark" ? "light" : "dark")), [setTheme])
  return { theme, toggle }
}

/** Tracks window history depth so Back/Forward can be disabled correctly (Electron same-document nav keeps state). */
export function useHistoryDepth() {
  const [depth, setDepth] = useState(() => (window.history.state?.idx as number | undefined) ?? 0)
  const [max, setMax] = useState(depth)
  useEffect(() => {
    const onPop = () => {
      const idx = (window.history.state?.idx as number | undefined) ?? 0
      setDepth(idx)
      setMax((m) => Math.max(m, idx))
    }
    window.addEventListener("popstate", onPop)
    return () => window.removeEventListener("popstate", onPop)
  }, [])
  return { canBack: depth > 0, canForward: depth < max }
}
