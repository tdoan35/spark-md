import { useCallback, useEffect, useMemo, useState } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { HashRouter, Routes, Route, useLocation, useNavigate, matchPath } from "react-router"
import { Toaster } from "@/components/ui/sonner"
import { TooltipProvider } from "@/components/ui/tooltip"
import { useSse } from "@/api/use-sse"
import { ApiError } from "@/api/client"
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

  const uid = matchPath("/study/:uid", loc.pathname)?.params.uid ?? null
  // A study reached straight from the worklist fills the active "New study" slot, so it owns a tab.
  const studyPath = useMemo(() => {
    const own = matchPath("/study/:uid", currentPathNoSearch(loc))
    if (!own) return null
    const slot = new URLSearchParams(loc.search).get("tab")
    return slot ? currentPathNoSearch(loc) : `/study/${own.params.uid}?tab=study-${own.params.uid}`
  }, [loc.pathname, loc.search])
  const slot = new URLSearchParams(loc.search).get("tab")
  const activeId = uid ? (slot ?? `study-${uid}`) : loc.pathname === "/" ? slot : null
  const currentPath = studyPath ?? loc.pathname + loc.search

  // Upsert the active slot on pathname/search changes (study tabs only).
  useEffect(() => {
    if (!activeId) return
    setTabs((t) => {
      const idx = t.findIndex((x) => x.id === activeId)
      if (idx === -1) return [...t, { id: activeId, path: currentPath, uid, label: "New study" }]
      if (t[idx].path === currentPath && t[idx].uid === uid) return t
      const next = [...t]
      next[idx] = { ...t[idx], path: currentPath, uid }
      return next
    })
  }, [activeId, currentPath, uid])

  const openWorklistTab = useCallback(() => navigate(`/?tab=${crypto.randomUUID()}`), [navigate])
  const newTab = openWorklistTab
  const closeTab = useCallback((id: string) => setTabs((t) => (t.some((x) => x.id === id) ? t.filter((x) => x.id !== id) : t)), [])

  const openStudy = useCallback(
    (studyUid: string) => {
      // Fill the active empty worklist slot if there is one; else reuse a study tab; else open a direct route.
      const empty = tabs.find((t) => t.uid === null && t.id === activeId)
      if (empty) return navigate(`/study/${studyUid}?tab=${empty.id}`)
      const existing = tabs.find((t) => t.uid === studyUid)
      if (existing) return navigate(existing.path)
      navigate(`/study/${studyUid}`)
    },
    [activeId, navigate, tabs],
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
        className="fixed bottom-(--footer-h) left-0 right-0 top-(--titlebar-h) transition-[padding] duration-200 ease-linear"
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

function currentPathNoSearch(loc: { pathname: string }) {
  return loc.pathname
}

function StudyRoute() {
  const loc = useLocation()
  const uid = matchPath("/study/:uid", loc.pathname)?.params.uid!
  return <StudyPage key={uid} uid={uid} />
}
