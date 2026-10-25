import { useCallback, useEffect, useMemo, useState } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { HashRouter, Routes, Route, useLocation, useNavigate, matchPath } from "react-router"
import { Toaster } from "@/components/ui/sonner"
import { TooltipProvider } from "@/components/ui/tooltip"
import { useStudy, useWorklist } from "@/api/hooks"
import { useSse } from "@/api/use-sse"
import { ApiError, API_BASE } from "@/api/client"
import { AppContext, type AppCtx } from "@/lib/app-context"
import { useTheme } from "@/lib/ui-hooks"
import { usePref } from "@/lib/prefs"
import { TitleBar, type ShellTab } from "@/shell/title-bar"
import { Sidebar } from "@/shell/sidebar"
import { Footer } from "@/shell/footer"
import { CommandSearch } from "@/shell/command-search"
import { WorklistPage } from "@/pages/worklist"
import { StudyPage } from "@/pages/study"
import { InboxPage } from "@/pages/inbox"
import { ActivityPage } from "@/components/agent-log"
import { SystemPage } from "@/pages/system"
import { ReplayBanner } from "@/shell/replay-banner"
import type { DemoState } from "@/api/types"

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5_000,
      refetchOnWindowFocus: false,
      retry: (n, e) => !(e instanceof ApiError && e.status >= 400 && e.status < 500) && n < 2,
    },
  },
})

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider delayDuration={300}>
        <HashRouter>
          <Shell />
        </HashRouter>
      </TooltipProvider>
    </QueryClientProvider>
  )
}

function Shell() {
  const sse = useSse()
  const { toggle: toggleTheme } = useTheme()
  const [sidebarOpen, setSidebarOpen] = usePref("sparkmd-sidebar-open", true)
  const [searchOpen, setSearchOpen] = useState(false)
  const [demo, setDemo] = useState<DemoState | null>(null)
  const navigate = useNavigate()
  const loc = useLocation()
  const [tabs, setTabs] = useState<ShellTab[]>([])

  useEffect(() => {
    const sub = sse.subscribe((t, d) => {
      if (t === "demo_state") setDemo(d as DemoState)
    })
    return sub
  }, [sse])
  // A reload mid-replay must still show the banner (SSE demo_state only fires on phase changes).
  useEffect(() => {
    fetch(`${API_BASE}/api/demo/state`).then((r) => (r.ok ? r.json() : null)).then((d) => d && setDemo((cur) => cur ?? (d as DemoState))).catch(() => {})
  }, [])

  const uid = matchPath("/study/:uid", loc.pathname)?.params.uid ?? null
  const { data: worklist } = useWorklist()
  const { data: activeStudy } = useStudy(uid)
  const patientOf = useCallback((studyUid: string | null) =>
    worklist?.find((s) => s.study_uid === studyUid)?.patient_id
      ?? (activeStudy?.study_uid === studyUid ? activeStudy.patient_id : undefined), [worklist, activeStudy])
  const patientId = patientOf(uid)
  const slot = new URLSearchParams(loc.search).get("tab")
  const activeId = uid ? (patientId ? `patient-${patientId}` : slot ?? `study-${uid}`) : loc.pathname === "/" ? slot : null
  const currentPath = loc.pathname + loc.search

  // Patient identity owns the slot; the URL still owns the selected study and history.
  useEffect(() => {
    if (!activeId) return
    setTabs((tabs) => {
      const next = tabs.filter((t) => t.id === activeId || !(
        (uid && t.uid === uid) ||
        (patientId && t.uid && patientOf(t.uid) === patientId) ||
        (uid && t.uid === null && t.id === slot)
      ))
      const idx = next.findIndex((t) => t.id === activeId)
      if (idx === -1) return [...next, { id: activeId, path: currentPath, uid, label: "New study" }]
      if (next.length === tabs.length && next[idx].path === currentPath && next[idx].uid === uid) return tabs
      next[idx] = { ...next[idx], path: currentPath, uid }
      return next
    })
  }, [activeId, currentPath, uid, patientId, patientOf, slot])

  const openWorklistTab = useCallback(() => navigate(`/?tab=${crypto.randomUUID()}`), [navigate])
  const newTab = openWorklistTab
  const closeTab = useCallback((id: string) => setTabs((t) => (t.some((x) => x.id === id) ? t.filter((x) => x.id !== id) : t)), [])

  const openStudy = useCallback(
    (studyUid: string) => {
      const patient = patientOf(studyUid)
      const existing = tabs.find((t) => t.uid === studyUid || (patient && t.uid && patientOf(t.uid) === patient))
      const empty = tabs.find((t) => t.uid === null && t.id === activeId)
      const id = existing?.id ?? empty?.id ?? (patient ? `patient-${patient}` : `study-${studyUid}`)
      navigate(`/study/${studyUid}?tab=${encodeURIComponent(id)}`)
    },
    [activeId, navigate, tabs, patientOf],
  )

  const ctx: AppCtx = useMemo(
    () => ({ sse, demo, openStudy, openWorklistTab, closeTab, toggleTheme, openSearch: () => setSearchOpen(true), newTab }),
    [sse, demo, openStudy, openWorklistTab, closeTab, toggleTheme, newTab],
  )
  return (
    <AppContext.Provider value={ctx}>
      <TitleBar tabs={tabs} activeId={activeId} sidebarOpen={sidebarOpen} onToggleSidebar={() => setSidebarOpen((v) => !v)} onCloseTab={closeTab} />
      <Sidebar expanded={sidebarOpen} />
      <main
        style={{ paddingLeft: sidebarOpen ? "calc(var(--sidebar-width) + 8px)" : "56px" }}
        className="fixed bottom-(--footer-h) left-0 right-2 top-(--titlebar-h) transition-[padding] duration-200 ease-linear"
      >
        <div className="relative h-full overflow-hidden rounded-xl border bg-background">
          <ReplayBanner demo={demo} uid={uid} />
          <Routes>
            <Route path="/" element={<WorklistPage />} />
            <Route path="/study/:uid" element={<StudyRoute />} />
            <Route path="/inbox" element={<InboxPage />} />
            <Route path="/activity" element={<ActivityPage />} />
            <Route path="/system" element={<SystemPage />} />
            <Route path="*" element={<WorklistPage />} />
          </Routes>
        </div>
      </main>
      <Footer />
      <CommandSearch open={searchOpen} onOpenChange={setSearchOpen} onPick={openStudy} />
      <Toaster position="top-center" offset={44} toastOptions={{ classNames: { description: "!text-muted-foreground" } }} />
    </AppContext.Provider>
  )
}

function StudyRoute() {
  const loc = useLocation()
  const uid = matchPath("/study/:uid", loc.pathname)?.params.uid!
  return <StudyPage key={uid} uid={uid} />
}
